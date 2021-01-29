#!/usr/bin/python3  `

""" The api.py module contains the classes and functions.
class tsSLD implements the Supervices Learning Data concept for modelled time series.
Auxuliary functions imports neural net models and AR models objects from predictor package/
"""

import copy
from os import getcwd,path
import sys
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import pmdarima as pm
import matplotlib.pyplot as plt


from clustgelDL.auxcfg import D_LOGS, log2All,exec_time
from predictor.utility import msg2log,shift,cSFMT
from predictor.NNmodel import MLP,LSTM,CNN
from predictor.Statmodel import tsARIMA
from stcgelDL.api import prepareLossCharts

""" NN model hyperparameters """
EPOCHS = 100  # training model
N_STEPS = 64
N_FEATURES = 1
UNITS = 32    # LSTM
FILTERS = 64  # CNN models
KERNEL_SIZE = 2
POOL_SIZE = 2
HIDDEN_NEYRONS = 16   # MLP model
DROPOUT = 0.2
""" ARIMA model hyperparameter """
SEASONALY_PERIOD = 6  # ARIMA 6- hour season , 144 for daily season
PREDICT_LAG = 4
MAX_P = 3
MAX_Q = 2
MAX_D = 2
PSD_SEGMENT_SIZE = 512

if sys.platform == 'win32':
    PATH_REPOSITORY = str(Path(Path(Path(getcwd()).drive) / '/' / "model_Repository"/ "offline_predictor"))
elif sys.platform == 'linux':
    PATH_REPOSITORY = str(Path(Path.home() / "model_Repository"/"offline_predictor"))

""" class definitions """

class tsSLD(object):
    def __init__(self,df:pd.DataFrame = None, data_col_name:str = None, dt_col_name:str = None, n_step:int = 32,
                 n_eval:int = 256, n_test:int = 64,bscaled:bool = False, discret:int = 10,f:object = None):

        df[dt_col_name] = pd.to_datetime(df[dt_col_name], dayfirst=True)
        self.data_col_name = data_col_name
        self.dt_col_name   = dt_col_name
        self.n       = len(df)
        self.y       = np.array(df[data_col_name])
        self.tlabs   = np.array(df[dt_col_name])

        self.n_step = n_step
        self.n_eval  = n_eval
        self.n_test  = n_test
        self.n_train = self.n - self.n_step - self.n_eval - self.n_test
        self.discret = discret
        self.X_train = np.zeros((self.n_train,self.n_step), dtype=float)
        self.y_train = np.zeros((self.n_train,), dtype=float)

        self.X_eval  = np.zeros((self.n_eval,self.n_step), dtype=float)
        self.y_eval  = np.zeros((self.n_eval,), dtype=float)

        self.X_test  = np.zeros((self.n_test, self.n_step), dtype=float)
        self.y_test  = np.zeros((self.n_test,), dtype=float)

        self.isScaled= bscaled
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.scalerY = MinMaxScaler(feature_range=(0, 1))

        self.f = f
        """ ARIMA parameters """
        self.p=0
        self.q=0
        self.d=0
        self.max_p=MAX_P
        self.max_d=MAX_D
        self.max_q=MAX_Q
        self.pP = 0
        self.qQ = 0
        self.dD = 0
        self.P = 0
        self.Q = 0
        self.D = 0
        self.max_P = 2
        self.max_D = 1
        self.max_Q = 1
        self.seasonaly_period=SEASONALY_PERIOD
        self.predict_lag=PREDICT_LAG
        self.psd_segment_size=min(512, 2**(len(bin(int(self.n/4)-1))-2))

        self.in_sample_start = -1  # It affects on ARIMA model forecasting
        self.predict_date=self.tlabs.max()
        pass

    def crtSLD(self):
        del self.X_train
        del self.X_eval
        del self.y_train
        del self.y_eval
        # if self.isScaled: TODO
        #     self.scalerY.fit(self.y[:self.n_train].reshape(-1,1))
        #     self.y[:self.n_train]=self.scalerY.transform(self.y[:self.n_train].reshape(-1,1))
        #     self.y[self.n_train:self.n_train+self.n_eval]=\
        #         self.scalerY.transform(self.y[self.n_train:self.n_train+self.n_eval].reshape(-1,1))
        #     self.y[self.n_train+self.n_eval:self.n] =\
        #         self.scalerY.transform(self.y[self.n_train+self.n_eval:self.n].reshape(-1,1))
        x=[]
        yy=[]
        for i in range(self.n_train):
            x.append(self.y[i:i+self.n_step])
            yy.append(self.y[i+self.n_step])
        self.X_train=np.array(x)
        self.y_train=np.array(yy)
        x=[]
        yy=[]
        for k in range(self.n_train,self.n_train+self.n_eval):

            x.append(self.y[k:k + self.n_step])
            yy.append(self.y[k+self.n_step])
        self.X_eval = np.array(x)
        self.y_eval = np.array(yy)
        x = []
        yy = []
        if self.n_test>0:
            del self.X_test
            del self.y_test
            for k in range(self.n_train + self.n_eval,self.n_train+self.n_eval +self.n_test):

                x.append(self.y[k:k + self.n_step])
                yy.append(self.y[k + self.n_step])
            self.X_test = np.array(x)
            self.y_test = np.array(yy)
        return

    def predSLD(self, start_in:int = None,ts:np.array = None)->np.array:
        """
        This method prepares Supervised Learning Data for predict by using NN models.
        For 'pure' forecasting on next time perion start_in should be 0.
        :param start_in: shift about last observation in TS
        :param ts:
        :return: np.array, SLD  matrix with nn -rows and self.n_step -columns. If start_in is set, nn=start_in+1,
                elese nn=1

        """

        msgErr = f"""Invalid generation set for prediction Supervised Learning Data. 
        Either an start index (offset of the end of the original time series (TS))  for intra prediction or 
        an independent segment of TS must be specified, but not both.
        If start index is specified then len(TS) - 'start index' should be greather than 'time step'.
        If TS segment is specified, its length should be greather than 'time step'. Otherwise lead zeros should be  
        added.
        """
        if start_in is None and ts is None:
            msg2log(None,msgErr,self.f)
            return None

        if (self.n-start_in<self.n_step and ts is None) or (self.n-start_in>=self.n_step and ts is not None):
            msg2log(None,msgErr,self.f)
            return None

        message=[]
        x = []
        zind = []
        """ predict into time series (TS)  """
        if ts is None:
            k_start=self.n -start_in-self.n_step
            k_end =k_start+self.n_step

            while k_end<=self.n :
                x.append(self.y[k_start:k_end])
                zind.append(k_end -1)
                k_start+=1
                k_end+=1
            message = \
                "In sample predict\nOffset of end TS: {} Start index into TS: {}".format(start_in, self.n-start_in-1)

        """ predict for new segment of TS """
        if ts is not None:
            (n,)=ts.shape
            if n<self.n_step:
                xx=[0.0 for r in range(self.n_step)]
                for i in range(self.n_step-n,self.n_step):
                    xx[i]=ts[i-self.n_step+n]
            x.append(xx)
            zind.append(0)
            message= "Out of sample predict TS."

        msg2log(None, message, D_LOGS['control'])
        x_pred = np.array(x)
        x_pred=x_pred.astype('float')
        (n, m) = x_pred.shape
        z = np.column_stack((zind, x_pred[:, :2], x_pred[:, m - 2:]))
        logMatrix(z, title="Index  X(t-{}) X(t-{})...X(t-2)  X(t-1)".format(self.n_step, self.n_step - 1),
                  f=D_LOGS['control'])
        return x_pred

    def ts_analysis(self):
        sModel="tsARIMA"
        sFolder = Path(D_LOGS['plot'] /Path(self.data_col_name)/Path(sModel))
        sFolder.mkdir(parents=True, exist_ok=True)
        self.d,self.D, _, _, _, _ = self.ts_preanalysis(self.psd_segment_size, str(sFolder))

        arima = tsARIMA("control_seasonal_arima", sModel, 32, 100, D_LOGS['control'])
        arima.param = (0, 0, 0, self.max_p, self.max_d, self.max_q, self.seasonaly_period, self.predict_lag,
                       self.discret, self.y)

        arima.path2modelrepository = PATH_REPOSITORY
        arima.timeseries_name = self.data_col_name
        arima.nameModel = 'control_seasonal_arima'
        arima.control_arima()
        (self.P,self.D,self.Q,S)=arima.model.seasonal_order
        (self.pP,self.dD,self.qQ) = arima.model.order
        tsARIMA.set_SARIMA((self.pP,self.dD,self.qQ, self.P,self.D,self.Q))
        tsARIMA._period=S
        tsARIMA._n_predict = self.predict_lag
        del arima

        arima1 = tsARIMA("control_best_arima", "tsARIMA", 32, 100, D_LOGS['control'])
        arima1.param = (0, 0, 0, self.max_p, self.max_d, self.max_q, self.seasonaly_period, self.predict_lag,
                        self.discret, self.y)

        arima1.path2modelrepository = PATH_REPOSITORY
        arima1.timeseries_name = self.data_col_name
        arima1.nameModel = 'control_best_arima'
        arima1.control_arima()
        (self.p,self.d,self.q)=arima1.model.order
        tsARIMA.set_ARIMA((self.p,self.d,self.q))
        del arima1
        (self.pP,self.dD,self.qQ,self.P,self.D,self.Q)=tsARIMA.get_SARIMA()
        S = tsARIMA._period
        message =f""" ARIMA orders
ar_order: {self.p} d_order: {self.d} ma_order: {self.q}
Seasonal:  {S} 
AR_order: {self.pP} D_order: {self.dD} MA_prder: {self.qQ} AR_order: {self.P} D_order: {self.D} MA_prder: {self.Q}

"""
        msg2log(None,message,self.f)
        return

    def ts_preanalysis(self, nfft: int,folder_name:str) -> (int,int,np.array, np.array, np.array, np.array):
        """

        :param nfft: segment size for FFT belongs to {16,32,64,  ..., 2^M}, M<12
        :param folder_name:
        :return:
        """
        Pxx   = None
        freqs = None
        line  = None
        alags = None
        acorr = None
        nfft  = min(nfft,2048)
        d     = 0
        D     = 0
        max_d = 5
        max_D = 3
        mean  = 0.0
        std   = 1.0
        message = ""
        try:
            d = pm.arima.ndiffs(self.y, 0.05, 'kpss', max_d)
            D = pm.arima.nsdiffs(self.y, self.seasonaly_period, self.max_D, 'ch')
            mean = np.mean(self.y)
            std  = np.std(self.y)
        except:
            message = f""" NDIFFS , NSDIFFS estimation.
Oops!! Unexpected error...
Error : {sys.exc_info()[0]}
"""
        finally:
            if len(message)>0:
                msg2log("ts_preanalysis", message, D_LOGS['except'])

        delta = self.discret * 60  # in sec
        N = len(self.y)
        Fs = 1.0 / delta
        maxFreq = 1.0 / (2 * delta)
        stepFreqPSD = 1.0 / (nfft * delta)

        message = f"""
Time series length        : {N}
FFT window length         : {nfft}
Discretization, sec       : {self.discret * 60}
Max.Frequency, Hz         : {maxFreq}
Freq. delta for PSD, Hz   : {stepFreqPSD}
Mean value                : {mean}
Std. value                : {std}
Max trend order           : {d}
Max seasonaly trend order : {D}
"""
        msg2log(None, message, D_LOGS['control'])

        normY=np.zeros((N),dtype=float)
        for i in range(len(self.y)):
            normY[i] = (self.y[i] - mean) / std

        plt.subplot(311)
        t = np.arange(0, len(self.y), 1)
        plt.plot(t, self.y)
        plt.subplot(312)

        message = ""
        try:
            Pxx, freqs, line = plt.psd(normY, nfft, Fs, return_line=True)
        except:
            message = f""" PSD estimation.
Oops!! Unexpected error...
Error : {sys.exc_info()[0]}
"""
        finally:
            if len(message)>0:
                msg2log("ts_preanalysis", message, D_LOGS['except'])

        plt.subplot(313)
        message = ""
        try:
            maxlags = min(250,int(len(self.y) / 4))
            alags   = None
            acorr   = None
            alags, acorr, line, b = plt.acorr(normY, maxlags=maxlags, normed=True)
            del normY
        except:
            message = f"""  Autocorrelation estimation.
Oops!! Unexpected error...
Error : {sys.exc_info()[0]}
"""
        finally:
            if len(message)>0:
                msg2log("ts_preanalysis", message, D_LOGS['except'])
        # plt.show(block=False)
        filePng = \
            Path( Path(folder_name) / Path("PwrSpecD_2sidesAutoCorr_{}".format(self.data_col_name))).with_suffix(".png")
        plt.savefig(filePng)
        plt.close("all")

        message=""
        try:
            nn,=freqs.shape
            freqs = freqs.reshape((nn, 1))
            Pxx = Pxx.reshape((nn, 1))
            a = np.append(freqs, Pxx, axis=1)

            fsp_name = Path(Path(folder_name) /Path("psd_{}".format(self.data_col_name))).with_suffix(".txt")
            with open (str(fsp_name),'w') as fsp:
                logMatrix(a, title='Power Spectral Density_{}\n NN   Frequence  Pxx'.format(self.data_col_name), f=fsp)

            nn,=alags.shape
            nnn:int = int((nn-1)/2) +1
            al=alags[nnn-1:].reshape((nnn,1))
            ac=acorr[nnn-1:].reshape((nnn,1))
            b=np.append(al,ac,axis=1)

            fcr_name = Path(Path(folder_name) / Path("autocorr_{}".format(self.data_col_name))).with_suffix(".txt")
            with open(str(fcr_name), 'w') as fcr:
                logMatrix(b, title='Autocorrelation_{}\n NN     Lag  Autocorrelation'.format(self.data_col_name), f=fcr)

        except:

            message = f"""PSD,ACORR logs preparing.
Oops!! Unexpected error...
Error : {sys.exc_info()[0]}
"""

        finally:
            if len(message)>0:
                msg2log("ts_preanalysis", message, D_LOGS['except'])

        return d,D, Pxx, freqs, acorr, alags

""" API definitions """

def logMatrix(X:np.array,title:str=None,f:object = None):
    if title is not None:
        msg2log(None,title,f)
    (n,m)=X.shape
    z=np.array([i for i in range(n)])
    z=z.reshape((n,1))
    a=np.append(z,X,axis=1)
    s = '\n'.join([''.join(['{:10.4f}'.format(item) for item in row]) for row in a])
    msg2log(None,"{}\n\n".format(s), f )

    return


def logMatrixVector(X:np.array, y:np.array, title:str=None,specification:str='fixed-point', f:object = None):
    """

    :param X:
    :param y:
    :param title:
    :param specification: 'fixed-point' for 10.4f format, 'scientific' for 10.4e format and 'decimal' for 10d format
    :param f:
    :return:
    """
    if title is not None:
        msg2log(None,title,f)
    (n,m)=X.shape

    z=np.array([i for i in range(n)])
    z=z.reshape((n,1))
    y1 = y.reshape((n, 1))
    a=np.append(z,X,axis=1)
    b=np.append(a,y1,axis=1)

    if m<100:
        s="\n{:<10s}".format("########")
        for i in range(m):
            if i<10:
                s = s + "    X[{:^1d}]   ".format(i)
            elif i>=10:
                s = s + "   X[{:^2d}]   ".format(i)

        s=s + "     {:^1s}     \n".format("Y")
        msg2log(None,s,f)

    # output string generation according by format specification
    if specification == 'fixed-point':
        s = '\n'.join([''.join([' {:10.4f}'.format(item) for item in row]) for row in b])
    elif specification == 'scientific':
        s = '\n'.join([''.join([' {:10.4e}'.format(item) for item in row]) for row in b])
    elif specification == 'decimal':
        s = '\n'.join([''.join([' {:10d}'.format(item) for item in row]) for row in b])
    else:
        s = '\n'.join([''.join([' {:10.4f}'.format(item) for item in row]) for row in b])
    msg2log(None,"{}\n\n".format(s),f)

    return

def isARIMAidentified():
    (p, d, q) = tsARIMA.get_ARIMA()
    (p1, d1, q1, P, D, Q) = tsARIMA.get_SARIMA()
    if (p > -1 and d > -1 and q > -1 and p1 > -1 and d1 > -1 and q1 > -1 and P > -1 and D > -1 and Q > -1):
        return ((p, d, q), (p1, d1, q1), (P, D, Q))
    else:
        return None

@exec_time
def d_models_assembly(d_models, keyType, valueList, sld:tsSLD = None):
    """

    :param d_models: dictionary {<index>:<wrapper for model>.
                     Through parameter <wrapper>.model, access to tensorflow model  is given.
    :param keyType: string value, type of NN model like as 'MLP','CNN','LSTM'
    :param valueList: tuple(index,model name) , i.e. (0,'mlp_1'),(1,'mlp_2') like as all models defined in cfg.py
    :param sld: instance of tsSLD class
    :return:
    """

    for tuple_item in valueList:
        index_model, name_model = tuple_item
        if keyType == "MLP":
            curr_model = MLP(name_model, keyType, sld.n_step, EPOCHS, D_LOGS['control'])
            curr_model.param = (sld.n_step, N_FEATURES, HIDDEN_NEYRONS, DROPOUT)
        elif keyType == "LSTM":
            curr_model = LSTM(name_model, keyType, sld.n_step, EPOCHS, D_LOGS['control'])
            curr_model.param = (UNITS, sld.n_step, N_FEATURES)
        elif keyType == "CNN":
            curr_model = CNN(name_model, keyType, sld.n_step, EPOCHS, D_LOGS['control'])
            curr_model.param = (sld.n_step, N_FEATURES)
        elif keyType == "tsARIMA":
            curr_model = tsARIMA(name_model, keyType, sld.n_step, EPOCHS, D_LOGS['control'])
            # reverse_arr=ds.df[cp.rcpower_dset].values[::-1]
            # For ARIMA passed certain orders which identifyed by ControlPlane  API
            status = isARIMAidentified()
            max_p = max_d = max_q = 3
            if status is not None:
                ((p, d, q), (p1, d1, q1), (P, D, Q)) = status
            else:
                p = d = q = p1 = d1 = q1 = P = D = Q = 0
                max_p = max_d = max_q = 2
            discretSec=sld.discret * 60
            if name_model == 'seasonal_arima':

                curr_model.param = (p1, d1, q1, P, D, Q, SEASONALY_PERIOD, PREDICT_LAG, discretSec,  sld.y)
            elif name_model == 'best_arima':

                curr_model.param = (p, d, q, max_p, max_d, max_q, SEASONALY_PERIOD, PREDICT_LAG, discretSec,  sld.y)
            else:
                smsg = "Undefined name of ARIMA {}\n It is not supported by STGELDP!".format(keyType)
                msg2log(None,smsg,D_LOGS['control'])
                return
        else:
            smsg = "Undefined type of Neuron Net or ARIMA {}\n It is not supported by STGELDP!".format(keyType)
            msg2log(None, smsg, D_LOGS['control'])
            return

        curr_model.path2modelrepository = PATH_REPOSITORY
        curr_model.timeseries_name = sld.data_col_name
        if keyType != "tsARIMA":  # no scaler for ARIMA
            curr_model.scaler = sld.scalerY

        funcname = getattr(curr_model, name_model)
        curr_model.set_model_from_template(funcname)
        # msg2log(None, str(curr_model),D_LOGS['train'])
        d_models[index_model] = curr_model
    log2All()
    return

@exec_time
def fit_models(d_models, sld:tsSLD, X_predict:np.array = None,in_sample_start:int = -1)->(dict,dict):
    """ A function fits NN models and AR models and makes a prediction by these models. If X_predict is None, the predict
    is not carried out.

    :param d_models:{ind:obj} where ind -index of the model, obj-compiled NN model or AR-model
    :param sld:  object tsSLD
    :param X_predict: vector for predicting, np.array  with shape (1,sld.n_step)
    :param in_sample_start: zero-indexed observation number an which to start forecasting or -1 (default). Be default,
        the forecasting is carried out starting for next period, ouf of the sample (observations of the time series).
        Or zero-based index of observation in the TS an which to start forecasting, i.e. test sequence.
    :return: histories is dictory of history object for NN models {ind:history}
             dict_predict {key:value} where key is obj.nameModel, value is a vector of predicts values,np.array with
    shape(sld.predict_lag)
    """
    pass
    """ A method fits NN models and STS models.

    :param d_models:  {ind:obj} where ind -index of the model, obj 
    :param sld:
    :param ds:
    :return:
    """
    histories = {}
    dict_predict={}
    vec_4_predict=None

    if X_predict is not None:
        (n, m) = X_predict.shape
        msg2log(None,"Predict data shape is {},{}".format(n,m), D_LOGS['train'])
        vec_4_predict = copy.copy(X_predict[0, :])
        vec_4_predict = vec_4_predict.astype('float')

    for k, v in d_models.items():
        curr_model = v

        X = copy.copy(sld.X_train)
        X_val = copy.copy(sld.X_eval)
        # #LSTM
        if curr_model.typeModel == "CNN" or curr_model.typeModel == "LSTM":
            X = X.reshape((X.shape[0], X.shape[1], N_FEATURES))
            X_val = X_val.reshape((X_val.shape[0], X_val.shape[1], N_FEATURES))
        folder_train_log = str(Path(path.realpath(D_LOGS['train'].name)).parent)
        folder_train_log=Path(D_LOGS['plot']/Path(sld.data_col_name)/Path(curr_model.typeModel))
        if not folder_train_log.is_dir():
            Path(folder_train_log).mkdir(parents=True, exist_ok=True)

        curr_model.param_fit = (
            X, sld.y_train, X_val, sld.y_eval, sld.n_step, N_FEATURES, EPOCHS, str(folder_train_log), D_LOGS['train'])
        msg2log(fit_models.__name__, "\n\n {} model  fitting\n".format(curr_model.nameModel), D_LOGS['train'])
        history = curr_model.fit_model()

        if curr_model.typeModel == "CNN" or curr_model.typeModel == "LSTM" or curr_model.typeModel == "MLP":

            prepareLossCharts(history,str(folder_train_log),D_LOGS['train'])
            if X_predict is not None:
                yy = np.zeros((sld.predict_lag),dtype=float)
                for kk in range(sld.predict_lag):
                    ypred = curr_model.predict_one_step(vec_4_predict)
                    # TODO inverse transform for scaled data

                    vec_4_predict = shift(vec_4_predict, -1, ypred)
                    yy[kk]=ypred
                dict_predict[curr_model.nameModel] =yy

                one_step_predicts_in_sampleNN(sld, curr_model, X_predict)

        elif curr_model.typeModel == "tsARIMA":
            curr_model.fitted_model_logging()

            dict_predict[curr_model.nameModel] = curr_model.predict
            # TODO
            # if in_sample_start is None:
            #     dict_predict[curr_model.nameModel] = curr_model.predict
            # else:
            #     dict_predict[curr_model.nameModel]= curr_model.predict_in_sample(start=in_sample_start,
            #                                                                      end=in_sample_start +sld.predict_lag)

        histories[k] = history

    log2All()
    return histories,dict_predict

def one_step_predicts_in_sampleNN(sld:tsSLD, curr_model:object, X_predict:np.array):

    (n,m) = X_predict.shape
    if n==1:
        return
    y_pred=np.zeros((n-1),dtype=float)
    e=np.zeros((n-1),dtype=float)
    abse=np.zeros((n-1),dtype=float)
    maxabse=0.0
    msg2log(None,"\n\n {} predict in sample by {}\n".format(sld.data_col_name, curr_model.nameModel),D_LOGS["predict"])
    header= "     {:<20s} {:<14s} {:<14s} {:<14s} {:<14s}".format(sld.dt_col_name, sld.data_col_name, "predict",
                                                                         "error", "abs.error")
    msg2log(None,header,D_LOGS["predict"])
    for i in range(1, n):
        y_pred[i-1] = curr_model.predict_one_step(X_predict[i,:])
        e[i-1]=sld.y[sld.n-i]-y_pred[i-1]
        abse[i-1]=abs(e[i-1])
        maxabse=max(maxabse,abse[i-1])
        ii=sld.n-1
        msg="{:>4d} {:<20s} {:<14.4f} {:<14.4f} {:<14.4f} {:<14.4f}".format(i-1, sld.tlabs[ii].strftime(cSFMT),
                                                                            sld.y[ii], y_pred[i-1], e[i-1], abse[i-1])
        msg2log(None,msg,D_LOGS['predict'])
    mean =e.mean()
    std  =e.std()
    message=f""" Prediction errors
mean : {mean}  std : {std} max abs(error): {maxabse}
"""
    msg2log(None,message,D_LOGS['predict'])

    """Prepares data for charting"""
    err_dict={}
    e=np.flip(e)
    y_pred=np.flip(y_pred)
    yobs=np.add(e,y_pred)
    err_dict['obs_index']=[i for i in range(sld.n-n,sld.n-1)]
    err_dict['error']=e
    err_dict['predict']=y_pred
    err_dict['observation']=yobs
    df=pd.DataFrame(err_dict)
    sFolder = Path(D_LOGS['plot'] / Path(sld.data_col_name) / Path(curr_model.typeModel))
    sFolder.mkdir(parents=True, exist_ok=True)
    title = "Test_Data_Predict_{}_{}".format(curr_model.nameModel, sld.data_col_name)
    test_predictions_file=Path(sFolder / Path(title)).with_suffix('.csv')
    df.to_csv(test_predictions_file,index=False)
    msg="{} test sequence predict by {} {} model saved in \n{}\n".format(sld.data_col_name, curr_model.typeModel,
                                                                         curr_model.nameModel, test_predictions_file)
    msg2log(None,msg,D_LOGS['predict'])

    plotPredictDF(test_predictions_file, sld.data_col_name, title= title)
    return


def bundlePredict(sld:tsSLD, dict_predict:dict, obs:np.array = None):

    columns = [key for key in dict_predict.keys()]
    columns.insert(0,sld.dt_col_name)

    if sld.in_sample_start is not None:
        columns.append(sld.data_col_name)

    header= "    {:<20s} ".format(sld.dt_col_name) + \
            ''.join(["{:<14s} ".format(item) for item in [key for key in dict_predict.keys()]])
    title="                The forecasting bundle "
    if sld.in_sample_start is None :
        title = title + "(in sample predict)"
        header +="{:<14s} ".format(sld.data_col_name)
    X=[]
    for k in range(sld.predict_lag):
        row = []

        row.append((sld.predict_date + timedelta(minutes=k*sld.discret)).strftime(cSFMT))
        for key,val in dict_predict.items():
            # (n,)=val.shape
            row.append(val[k])
        if sld.in_sample_start is not None:
            row.append(sld.y[sld.in_sample_start+k])
        X.append(row)
    msg2log(None,"\n\n{}\n{}\n".format(title, header), D_LOGS['predict'])

    k=0
    for row in X:
        temp_prnt="{:>3d} {:<20s} ".format(k, row[0])
        temp_prnt=temp_prnt + ''.join(["{:>14.6f}".format(item) for item in row[1:]])
        msg2log(None,temp_prnt,D_LOGS['predict'])

    df=pd.DataFrame(X)
    df.columns=columns
    csv_predict = \
        Path(path.realpath(D_LOGS['predict'].name)).parent /Path("predict_{}".format(sld.data_col_name)).with_suffix(".csv")
    df.to_csv(csv_predict,index=False)
    plotPredictDF(csv_predict, sld.data_col_name, title= "Forecasting_bandle")
    return

def plotPredictDF(bundle_predictions_file:str, data_col_name:str,title:str = "Forecasting_bandle"):

    suffics = '.png'
    bundle_predictions_png = Path(D_LOGS['plot'] / Path(data_col_name)/Path(title)).with_suffix(suffics)
    df = pd.read_csv(bundle_predictions_file)
    df.head()
    try:
        df.plot(x=df.columns.values[0], y=df.columns.values[1:], kind='line')
        numfig = plt.gcf().number
        fig = plt.figure(num=numfig)
        fig.set_size_inches(18.5, 10.5)
        fig.suptitle("The bundle of {} predictions".format(data_col_name), fontsize=24)

        plt.savefig(bundle_predictions_png)
        message = f"""
The new predictions csv saved           : {bundle_predictions_file}
The bundle of the predictions png saved : {bundle_predictions_png}
        """
        msg2log(None, message, D_LOGS['predict'])
    except:
        pass
    finally:
        plt.close("all")
    return