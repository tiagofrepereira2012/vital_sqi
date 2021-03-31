"""R peak detection approaches for PPG and ECG"""
import numpy as np
from sklearn.cluster import KMeans
from scipy import signal

from vital_sqi.preprocess.band_filter import BandpassFilter
from vital_sqi.common.generate_template import ecg_dynamic_template
import warnings
from ecgdetectors import Detectors,panPeakDetect


class PeakDetector:
    """Various peak detection approaches getting from the paper
    Systolic Peak Detection in Acceleration Photoplethysmograms Measured
    from Emergency Responders in Tropical Conditions

    Parameters
    ----------

    Returns
    -------

    """
    def __init__(self, wave_type='ppg'):
        self.clusters = 2
        self.wavet_type = wave_type


    def ecg_detector(self,s,fs=256,detector_type="pan_tompkins"):
        """
        Expose

        ECG peak detector from the github https://github.com/berndporr/py-ecg-detectors

        Parameters
        ----------
        s :
            Input signal

        fs:
            The signal frequency. Default is '256 Hz'

        detector_type:
            'hamilton': Open Source ECG Analysis Software Documentation, E.P.Limited, 2002.

            'christov':Real time electrocardiogram QRS detection using combined
            adaptive threshold

            'engzee': A single scan algorithm for QRS detection and
            feature extraction

            'swt': Real-time QRS detector using Stationary Wavelet Transform for Automated ECG Analysis.
            Uses the Pan and Tompkins thresolding.

            'mva': Frequency Bands Effects on QRS Detection.

            'mtemp':

            'pan_tompkins': A Real-Time QRS Detection Algorithm

            Default = 'pan_tompkins'


        Returns
        -------
        type
            an array of 1-D numpy array represent the peak list

        """
        if self.wave_type =='ppg':
            warnings.warn("A ECG detectors is using on PPG waveform. Output may produce incorrect result")
        self.fs = fs
        detector = Detectors(fs)
        if detector_type == 'hamilton':
            res = detector.hamilton_detector(s)
        elif detector_type == 'christov':
            res = detector.christov_detector(s)
        elif detector_type == 'engzee':
            res = detector.engzee_detector(s)
        elif detector_type == 'swt':
            res = detector.swt_detector(s)
        elif detector_type == 'mva':
            res = detector.two_average_detector(s)
        elif detector_type == 'mtemp':
            res = self.matched_filter_detector(s)
        else:
            res = detector.pan_tompkins_detector(s)
        return np.array(res)

    def ppg_detector(self,s,detector_type="count_orig",clusterer="kmean",preprocess = True,cubing=False):
        """
        Expose

        PPG peak detector from the paper
        Systolic Peak Detection in Acceleration Photoplethysmograms Measured
        from Emergency Responders in Tropical Conditions

        :param s: the input signal
        :param detector_type:
        :param clusterer:
        :return:
        """

        if preprocess:
            filter = BandpassFilter()
            s = filter.signal_highpass_filter(s, cutoff=1, fs=100, order=2)
            s = filter.signal_lowpass_filter(s, cutoff=12, fs=100, order=2)
        if  cubing:
            s = s**3

        if self.wavet_type != "ppg":
            warnings.warn("A PPG detectors is using on  unrecognized PPG waveform. Output may produce incorrect result")

        try:
            if detector_type == "cluster":
                peak_finalist, through_finalist = self.detect_peak_trough_clusterer(s)
            elif detector_type == "slope_sum":
                peak_finalist, through_finalist = self.detect_peak_trough_slope_sum(s)
            elif detector_type == "moving_average":
                peak_finalist, through_finalist = self.detect_peak_trough_moving_average_threshold(s)
            else:
                peak_finalist, through_finalist = self.detect_peak_trough_count_orig(s)
        except Exception as err:
            print(err)
            return signal.find_peaks(s),[]

        return peak_finalist,through_finalist

    def matched_filter_detector(self, unfiltered_ecg):
        """
        handy
        FIR matched filter using template of QRS complex.
        Template provided in generate_template file
        """
        template = ecg_dynamic_template(self.fs)

        f0 = 0.1 / self.fs
        f1 = 48 / self.fs

        b, a = signal.butter(4, [f0 * 2, f1 * 2], btype='bandpass')

        prefiltered_ecg = signal.lfilter(b, a, unfiltered_ecg)

        matched_coeffs = template[::-1]  # time reversing template

        detection = signal.lfilter(matched_coeffs, 1, prefiltered_ecg)  # matched filter FIR filtering
        squared = detection * detection  # squaring matched filter output
        squared[:len(template)] = 0

        squared_peaks = panPeakDetect(squared, self.fs)

        return squared_peaks

    def compute_feature(self, s, local_extrema):
        """
        handy
        Parameters
        ----------
        s :
            
        local_extrema :
            

        Returns
        -------

        """
        amplitude = s[local_extrema]
        diff = np.diff(amplitude)
        diff = np.hstack((diff[0], diff, diff[-1]))
        mean_diff = np.mean(np.vstack((diff[1:], diff[:-1])), axis=0)
        amplitude = amplitude.reshape(-1, 1)
        mean_diff = mean_diff.reshape(-1, 1)
        return np.hstack((amplitude, mean_diff))

    def detect_peak_trough_clusterer(self,s,clusterer='kmean',**kwargs):
        """
        handy
        Method 1: using clustering technique

        Parameters
        ----------
        s :
            The input signals
        method :
            param kwargs:
        **kwargs :
            

        Returns
        -------
        type
            tuple of 1-D numpy array
            the first array is the peak list and the second array is the troughs list

        """
        # squarring doesnot work
        # s = np.array(s) ** 2
        local_maxima = signal.argrelmax(s)[0]
        local_minima = signal.argrelmin(s)[0]
        local_minima_amplitude = s[local_minima]
        local_maxima_amplitude = s[local_maxima]
        lower, middle, upper = np.quantile(s, [0.25, 0.5, 0.75])

        # clusterer = KMeans(kwargs)
        clusterer = KMeans(n_clusters=2, init='k-means++', n_init=10, max_iter=300,
                           tol=0.0001, precompute_distances='deprecated', verbose=0,
                           random_state=None, copy_x=True, n_jobs='deprecated', algorithm='auto')

        convert_maxima = self.compute_feature(s, local_maxima)
        clusterer.fit(convert_maxima)
        systolic_group = clusterer.predict(convert_maxima[np.argmax(s[local_maxima])].reshape(1, -1))
        labels = clusterer.predict(convert_maxima)

        systolic_peaks_idx = local_maxima[np.where(labels == systolic_group)]

        # ========================================================
        # The same with troughs

        convert_minima = self.compute_feature(s, local_minima)
        clusterer.fit(convert_minima)
        trough_group = clusterer.predict(convert_minima[np.argmin(s[local_minima])].reshape(1, -1))
        labels = clusterer.predict(convert_minima)

        trough_idx = local_minima[np.where(labels == trough_group)]

        return systolic_peaks_idx, trough_idx

    def detect_peak_trough_count_orig(self,s):
        """
        handy
        Method 2: using local extreme technique with threshold

        Parameters
        ----------
        s :
            Input signal

        Returns
        -------
        type
            tuple of 1-D numpy array
            the first array is the peak list and the second array is the troughs list

        """
        #squaring decrease the efficiency
        # s = np.array(s)**2

        local_maxima = signal.argrelmax(s)[0]
        local_minima = signal.argrelmin(s)[0]

        peak_threshold = np.quantile(s[local_maxima], 0.75) * 0.2
        trough_threshold = np.quantile(s[local_minima], 0.25) * 0.2

        peak_shortlist = np.array([optima for optima in local_maxima if s[optima] >= peak_threshold])
        trough_shortlist = np.array([optima for optima in local_minima if s[optima] <= trough_threshold])

        peak_finalist = []
        through_finalist = []
        left_trough = trough_shortlist[0]
        for i in range(1,len(trough_shortlist)):

            right_trough = trough_shortlist[i]
            peaks = [peak for peak in peak_shortlist if peak < right_trough and peak > left_trough]
            if len(peaks) == 0:
                left_trough = np.array([left_trough,right_trough])[np.argmin([s[left_trough],s[right_trough]])]
            else:
                peak = peaks[np.argmax(s[peaks])]
                peak_finalist.append(peak)
                through_finalist.append(left_trough)
                left_trough = right_trough
        through_finalist.append(right_trough)
        return peak_finalist,through_finalist

    def detect_peak_trough_slope_sum(self,s):
        """
        handy
        Method 3: analyze the slope sum to get local extreme

        Parameters
        ----------
        s :
            return:

        Returns
        -------

        """
        peak_finalist = []
        trough_finalist = []
        onset_list = []
        """
        Here w is the length of the analysing window, which Zong et al. [25] 
        approximate to be equal to 128 ms or 47 samples 
        for the sampling frequency (fs) of 367 Hz
        """
        w = 12
        N = len(s)
        Z = []
        n_range = np.arange(w+1,N)

        for n in n_range:
            Zk=0
            for k in range((n - w),n):
                delta_y_k = s[k] - s[k-1]
                Zk = Zk + max(0,delta_y_k)
            Z.append(Zk)
        Z = np.array(Z)

        fs = 100
        Z_threshold = 3 * np.mean(Z[:10*fs])
        threshold_base = Z_threshold

        for n in range(len(Z)):
            actual_threshold = threshold_base * 0.6
            if Z[n] > actual_threshold:
                left = n-15
                right = n+15
                if left < 0:
                    left = 0
                if right > len(Z):
                    right = len(Z)
                local_min = np.min(Z[left:right])
                local_max = np.max(Z[left:right])
                if (local_max - local_min) > local_min*2:
                    # Accept the pulse
                    threshold_crossing_point = n
                    onset = self.search_for_onset(Z,threshold_crossing_point,local_max)
                    onset_list.append(onset)
                    # peak_finalist.append(threshold_crossing_point+np.argmax())
                #maximum Z[n] value for each pulse detected
                threshold_base = local_max #?????

        onset_list = np.array(list(set(onset_list)))
        onset_list.sort()
        for trough_idx in range(1,len(onset_list)):
            left = onset_list[trough_idx-1]
            right = onset_list[trough_idx]
            try:
                peak_finalist.append(np.argmax(s[left:right])+left)
                trough_finalist.append(np.argmin(s[left:right]) + left)
            except Exception as e:
                print(e)
        return peak_finalist, onset_list

    def search_for_onset(Z,idx,local_max):
        """
        handy
        Parameters
        ----------
        Z :
            
        idx :
            
        local_max :
            

        Returns
        -------

        """
        # while Z[idx] > 0.01*local_max:
        while Z[idx] > 0:
            idx = idx -1
            if idx <= 0:
                return idx
        return idx+1

    def detect_peak_trough_moving_average_threshold(self,s):
        """
        handy
        Method 4 (examine second derivative)

        Parameters
        ----------
        s :
            return:

        Returns
        -------

        """
        peak_finalist = []
        through_finalist = []

        #Bandpass filter
        filter = BandpassFilter()
        S = filter.signal_highpass_filter(s,0.5,fs=100)
        # S = butter_lowpass_filter(S,8,fs=100)
        # S = s
        #Clipping the output by keeping the signal above zero will produce signal Z
        Z = np.array([np.max([0,z]) for z in S])
        #Squaring suppressing the small differences arising from the diastolic wave and noise
        y = Z**2

        w1 = 12 #111ms
        w2 = 67 #678ms
        #MA_peak
        ma_peak = self.get_moving_average(y,w1)
        #MA_beat
        ma_beat = self.get_moving_average(y,w2)
        # Thresholding
        z_mean = np.mean(y)
        beta = 0.02
        alpha = beta*z_mean+ma_beat
        thr1 = ma_beat + alpha
        block_of_interest = np.zeros(len(thr1))
        for i in range(len(ma_peak)):
            if ma_peak[i] > thr1[i]:
                block_of_interest[i] = 0.1

        # Accept and Reject block of interest
        # If a block is wider than or equal to THR2, it is classified as a systolic peak
        thr2 = w1
        BOI_idx = np.where(block_of_interest > 0)[0]  # index of the signal having boi == 0.1
        BOI_diff = np.diff(BOI_idx) # the different of consequence BOI
        BOI_width_idx = np.where(BOI_diff > 1)[0]  # index where the block move to other block

        for i in range(len(BOI_width_idx)):
            if i == 0:
                BOI_width = BOI_width_idx[i]
            else:
                BOI_width = BOI_width_idx[i] - BOI_width_idx[i - 1]

            if BOI_width >= thr2:
                if i == 0:
                    left_idx = 0
                else:
                    left_idx = BOI_width_idx[i-1]
                # left_idx = BOI_width_idx[np.max([0,i-1])]
                right_idx = BOI_width_idx[i]
                region = y[BOI_idx[left_idx]:BOI_idx[right_idx]+1]
                peak_finalist.append(BOI_idx[left_idx] + np.argmax(region))

        return peak_finalist,through_finalist

    def get_moving_average(self,q,w):
        """
        handy
        Parameters
        ----------
        q :
            
        w :
            

        Returns
        -------

        """
        # shifting = np.ceil(w-w/2)-1
        # remaining = w-1-shifting
        q_padded = np.pad(q, (w // 2, w - 1 - w // 2), mode='edge')
        convole = np.convolve(q_padded, np.ones(w)/w, 'valid')
        return convole
