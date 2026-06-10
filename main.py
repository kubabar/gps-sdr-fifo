import sys
import os
import os.path
import subprocess
import io
import gzip
from ftplib import FTP_TLS
from datetime import datetime, timedelta, timezone
from time import time, sleep
from subprocess import Popen
from pathlib import Path
import numpy as np
import SoapySDR
import threading


import ipdb
try:
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton, QDoubleSpinBox, QSlider, QGridLayout, QSpinBox
    from PySide6.QtCore import QTimer, Qt
except ImportError:
    print("Using PyQt5")
    from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton, QDoubleSpinBox, QSlider, QGridLayout, QSpinBox
    from PyQt5.QtCore import QTimer, Qt


class DPadWidget(QWidget):
    def __init__(self, spinbox_updown, spinbox_leftright, speed_slider, speed_label, step, parent=None):
        super().__init__(parent)

        # Store references to the QDoubleSpinBox widgets, the speed slider, and the speed label
        self.spinbox_updown = spinbox_updown
        self.spinbox_leftright = spinbox_leftright
        self.speed_slider = speed_slider
        self.speed_label = speed_label

        # Create buttons for each direction
        self.up_button = QPushButton('▲', self)
        self.left_button = QPushButton('◀', self)
        self.down_button = QPushButton('▼', self)
        self.right_button = QPushButton('▶', self)

        # Set up layout
        layout = QGridLayout(self)
        layout.addWidget(self.up_button, 0, 1)
        layout.addWidget(self.left_button, 1, 0)
        layout.addWidget(self.down_button, 2, 1)
        layout.addWidget(self.right_button, 1, 2)
        layout.addWidget(self.speed_slider, 3, 0, 1, 2)
        layout.addWidget(self.speed_label, 3, 2)

        # Set initial speed and step
        self.step = step  # corresponds to 6 decimal places

        # Create timers
        self.up_timer = QTimer(self)
        self.left_timer = QTimer(self)
        self.down_timer = QTimer(self)
        self.right_timer = QTimer(self)

        # Connect timer signals
        self.up_timer.timeout.connect(self.move_up)
        self.left_timer.timeout.connect(self.move_left)
        self.down_timer.timeout.connect(self.move_down)
        self.right_timer.timeout.connect(self.move_right)

        # Connect button press and release signals
        self.up_button.pressed.connect(self.up_timer.start)
        self.up_button.released.connect(self.up_timer.stop)
        self.left_button.pressed.connect(self.left_timer.start)
        self.left_button.released.connect(self.left_timer.stop)
        self.down_button.pressed.connect(self.down_timer.start)
        self.down_button.released.connect(self.down_timer.stop)
        self.right_button.pressed.connect(self.right_timer.start)
        self.right_button.released.connect(self.right_timer.stop)

        # Connect slider value change signal
        self.speed_slider.valueChanged.connect(self.update_speed)

        # Update the speed label initially
        self.update_speed_label()

    def move_up(self):
        current_value = self.spinbox_updown.value()
        self.spinbox_updown.setValue(current_value + self.step)

    def move_left(self):
        current_value = self.spinbox_leftright.value()
        self.spinbox_leftright.setValue(current_value - self.step)

    def move_down(self):
        current_value = self.spinbox_updown.value()
        self.spinbox_updown.setValue(current_value - self.step)

    def move_right(self):
        current_value = self.spinbox_leftright.value()
        self.spinbox_leftright.setValue(current_value + self.step)

    def update_speed(self, value):
        # Calculate reciprocal to represent speed
        reciprocal_speed = 1 / value
        self.update_speed_label()

        # Update timer intervals based on the new speed
        self.up_timer.setInterval(reciprocal_speed * 1000)
        self.left_timer.setInterval(reciprocal_speed * 1000)
        self.down_timer.setInterval(reciprocal_speed * 1000)
        self.right_timer.setInterval(reciprocal_speed * 1000)

    def update_speed_label(self):
        # Calculate the rate of change in degrees per second
        degrees_per_second = self.step * self.speed_slider.value()
        self.speed_label.setText(f"Szybkość: {degrees_per_second:.6f} °/s")

class LocationWidget(QWidget):
    def __init__(self, step, parent=None):
        super().__init__(parent)

        # Create QDoubleSpinBox widgets
        self.spinbox_updown = QDoubleSpinBox(self)
        self.spinbox_leftright = QDoubleSpinBox(self)
        self.spinbox_elevation = QDoubleSpinBox(self)
        
        
        self.step = step

        # Set the number of decimals for each spin box
        self.spinbox_updown.setDecimals(6)
        self.spinbox_leftright.setDecimals(6)
        self.spinbox_elevation.setDecimals(1)

        # Set the range to allow negative numbers
        self.spinbox_updown.setRange(-90.000000, 90.000000)
        self.spinbox_leftright.setRange(-180.000000, 180.000000)
        self.spinbox_elevation.setRange(-10000.0, 10000.0)
        
        # Add degree sign at the end of the boxes
        self.spinbox_updown.setSuffix("°")
        self.spinbox_leftright.setSuffix("°")
        self.spinbox_elevation.setSuffix(" m")
        
        # Set step to 0.000001 and enable acceleration
        self.spinbox_updown.setSingleStep(self.step)
        self.spinbox_leftright.setSingleStep(self.step)
        self.spinbox_elevation.setSingleStep(0.1)
        
        self.spinbox_updown.setAccelerated(True)
        self.spinbox_leftright.setAccelerated(True)
        self.spinbox_elevation.setAccelerated(True)
        
        # Set default values
        # 39.316380, -74.522388
        self.spinbox_updown.setValue(39.316380)
        self.spinbox_leftright.setValue(-74.522388)
        self.spinbox_elevation.setValue(50.0)
        
        # Bind value getters to self
        self.getLat=self.spinbox_updown.value
        self.getLon=self.spinbox_leftright.value
        self.getHi =self.spinbox_elevation.value
        
        
        # Create QSlider for controlling speed
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(1000)
        self.speed_slider.setValue(50)  # Default speed

        # Create QLabel to display the speed value
        self.speed_label = QLabel(self)

        # Create DPadWidget with references to the QDoubleSpinBox widgets, the speed slider, and the speed label
        self.location_widget_widget = DPadWidget(self.spinbox_updown, self.spinbox_leftright, self.speed_slider, self.speed_label, self.step, self)

        # Set up layout
        layout = QGridLayout(self)
        
        # Add labels
        lat_label = QLabel('Szerokość')
        lon_label = QLabel('Długość')
        hi_label = QLabel('Wysokość')
        
        layout.addWidget(self.spinbox_updown, 0, 1)
        layout.addWidget(self.spinbox_leftright, 1, 1)
        layout.addWidget(self.spinbox_elevation, 2, 1)
        
        layout.addWidget(lat_label, 0, 0)
        layout.addWidget(lon_label, 1, 0)
        layout.addWidget(hi_label, 2, 0)
        
        layout.addWidget(self.speed_slider, 3, 0, 1, 2)
        layout.addWidget(self.speed_label, 4, 0, 1, 2)
        layout.addWidget(self.location_widget_widget, 5, 0, 1, 2)

class ParameterPrinter(QWidget):
    def __init__(self, dynamicparameters, staticparameters, fifo, fifocsv):
        super().__init__()
        self.dynamicparameters = dynamicparameters
        self.staticparameters = staticparameters
        self.subprocessgpssim = None
        self.subprocesstransfer = None
        self.fifo=fifo
        self.fifocsv=fifocsv

        #self.resize(1000,400)
        self.timer = QTimer()
        self.timer.timeout.connect(self.timerTick)
        self.timer.start(100)
        self.offset_counter=0.1 # zeby gps zdazyl nadrobic opoznienie
        self.base_date=datetime.now()
        self.fifo_started=False
        self.process_started = False
        self.gain=0
        self.initUI()

    def initUI(self):
        app_layout = QVBoxLayout(self)

        column_labels_layout = QHBoxLayout()
        dynamicparams_label = QLabel("Lokalizacja")
        dynamicparams_label.setAlignment(Qt.AlignLeft)

        staticparams_label = QLabel("Parametry początkowe (statyczne)")
        staticparams_label.setAlignment(Qt.AlignRight)
        column_labels_layout.addWidget(dynamicparams_label)
        column_labels_layout.addWidget(staticparams_label)
        app_layout.addLayout(column_labels_layout)

        rows_layout = QHBoxLayout()
        
        dynamicparams_layout = QVBoxLayout()
        self.staticparams_layout = QVBoxLayout()
        start_stop_layout = QVBoxLayout()
        dynamicparams_layout.setAlignment(Qt.AlignTop)
        self.staticparams_layout.setAlignment(Qt.AlignTop)
        start_stop_layout.setAlignment(Qt.AlignTop)

        for key, value in self.staticparameters.items():
            row_layout = QHBoxLayout()
            label = QLabel(key)
            explanation_label = QLabel(value[0])
            line_edit = QLineEdit(str(value[1]))

            row_layout.addWidget(label)
            row_layout.addWidget(explanation_label)
            row_layout.addWidget(line_edit)
            self.staticparams_layout.addLayout(row_layout)
            setattr(self, f"line_edit_{key}", line_edit)
        
        self.spinbox_gain = QSpinBox()
        self.spinbox_gain.setMaximum(47)
        self.spinbox_gain.setSuffix(" dB")
        self.spinbox_gain.valueChanged.connect(self.on_gain_changed)
        
        
        new_layout = QHBoxLayout()
        self.datelabel = QLabel("datetime")
        new_layout.addWidget(self.datelabel)
        self.staticparams_layout.addWidget(self.spinbox_gain)
        self.staticparams_layout.addLayout(new_layout)
        
        
        
        self.start_button = QPushButton('Start', self)
        self.start_button.clicked.connect(self.start_event)

        self.stop_button = QPushButton('Stop', self)
        self.stop_button.clicked.connect(self.stop_event)
        self.stop_button.setEnabled(False)
        
        self.download_button = QPushButton('Pobierz efemer.', self)
        self.download_button.clicked.connect(self.pobierz_efemeryde)
        
        start_stop_layout.addWidget(self.start_button)
        start_stop_layout.addWidget(self.stop_button)
        start_stop_layout.addWidget(self.download_button)
        
        
        self.location_widget=LocationWidget(0.000001)
        dynamicparams_layout.addWidget(self.location_widget)
        
        rows_layout.addLayout(dynamicparams_layout)
        rows_layout.addLayout(self.staticparams_layout)
        rows_layout.addLayout(start_stop_layout)

        app_layout.addLayout(rows_layout)
        app_layout.setAlignment(Qt.AlignTop)
        #ipdb.set_trace()
    
    def on_gain_changed(self, gain):
        self.gain = gain
        if self.fifo_started:
            self.sdr.setGain(SoapySDR.SOAPY_SDR_TX, 0, 'VGA', float(gain))
    
    def rm_fifos(self):
        if os.path.exists(self.fifo):
            os.remove(self.fifo)
        if os.path.exists(self.fifocsv):
            os.remove(self.fifocsv)
        self.fifo_started=False
        print("rmfifo")
      
    def make_fifos(self):
        self.rm_fifos()
        os.mkfifo(self.fifo)
        os.mkfifo(self.fifocsv)
    
    def start_fifocsv(self):
        while_sanity=10
        while not self.fifo_started and while_sanity:
            try:
                self.fifocsvwriter=os.open(self.fifocsv, os.O_WRONLY | os.O_NONBLOCK)
                self.fifo_started=True
                print("started csv fifo")
            except OSError as e:
                print(e)
                #self.stop_event()
                while_sanity-=1
                sleep(0.1)
    
    def pobierz_efemeryde(self, rok=None, nazwa='brdc.n', last=False):
        if not rok:
            rok = datetime.now().astimezone(timezone.utc).year

        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # CDDIS cert can cause issues

        ftps = FTP_TLS(host='gdc.cddis.eosdis.nasa.gov', context=ctx, timeout=30)
        try:
            ftps.login(user='', passwd='')
            ftps.prot_p()
            ftps.set_pasv(True)

            # ftp://gdc.cddis.eosdis.nasa.gov/pub/gps/data/daily/2023/brdc/brdc3120.23n.gz
            ftps.cwd(f"/pub/gps/data/daily/{rok}/brdc")
            files = ftps.nlst()
            filename = None
            lastdob = None
            unzipfn = nazwa
            unlastdob = "last_" + nazwa
            for fn in files[::-1]:
                if fn[-4:] == 'n.gz':
                    if filename == None:
                        filename = fn
                        if not last:
                            break
                    else:
                        lastdob = fn
                        break

            if filename == None or lastdob == None and last:
                print("Nie znalzeiono efemerydy")
                return

            ftps.retrbinary("RETR " + filename, open(filename, 'wb').write)
            with gzip.open(filename, 'rb') as f:
                with open(unzipfn, 'wb') as uf:
                    uf.write(f.read())
            if last:
                ftps.retrbinary("RETR " + lastdob, open(lastdob, 'wb').write)
                with gzip.open(lastdob, 'rb') as f:
                    with open(unlastdob, 'wb') as uf:
                        uf.write(f.read())

        finally:
            try:
                ftps.quit()
            except Exception:
                ftps.close()
    
    def start_event(self):
        if 1 or self.subprocessgpssim is None or self.subprocessgpssim.poll() is not None:
            self.update_dynamicparameters()
            self.update_staticparameters()
            self.make_fifos()
            #ipdb.set_trace()
            
            self.transferthread=threading.Thread(target=self.send_iq_file)
            self.transferthread.start()
            
            self.subprocessgpssim = Popen(['./gpssim-dyn', '-b', '8', '-e', self.staticparameters['-e'], '-T', self.formatted_date, '-s', self.staticparameters['-s'], '-x', self.fifocsv, '-o', self.fifo, '-v'])

            self.start_fifocsv()
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.set_locks(True)
            self.process_started = True

    def stop_event(self):
        if self.subprocessgpssim and self.subprocessgpssim.poll() is None:
            self.subprocessgpssim.terminate()
            self.subprocessgpssim.wait()
        #ipdb.set_trace()
        self.rm_fifos()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.set_locks(False)
        self.process_started = False
        print("stop event finish")
    
    def set_locks(self, state):
        for key in self.staticparameters.keys():
            line_edit = getattr(self, f"line_edit_{key}")
            line_edit.setEnabled(not bool(state))
    
    def update_dynamicparameters(self):
        self.dynamicparameters['lat']= format(self.location_widget.getLat(), '.6f')
        self.dynamicparameters['lon']= format(self.location_widget.getLon(), '.6f')
        self.dynamicparameters['hi'] = format(self.location_widget.getHi(),  '.1f')
        
    def update_staticparameters(self):
        for key in self.staticparameters.keys():
            line_edit = getattr(self, f"line_edit_{key}")
            self.staticparameters[key] = line_edit.text()
        
    def timerTick(self):
        self.update_dynamicparameters()
        self.offset_counter+=0.1
        self.new_date = self.base_date + timedelta(seconds=self.offset_counter)
        self.utc_date = self.new_date.astimezone(timezone.utc)
        self.formatted_date = self.utc_date.strftime("%Y/%m/%d,%H:%M:%S")
        self.datelabel.setText(self.formatted_date)
        if self.process_started:
            self.loco=f"{round(self.offset_counter,1)},{self.dynamicparameters['lat']},{self.dynamicparameters['lon']},{self.dynamicparameters['hi']}\n"
            if self.fifo_started:
                os.write(self.fifocsvwriter, self.loco.encode())
                print('    '+self.loco, end='')
                #ipdb.set_trace()
        

    def send_iq_file(self):
        file_path = self.fifo
        device_args = 'driver=hackrf'
        sample_rate=float(self.staticparameters['-s'])
        center_freq=float(self.staticparameters['-f'])
        gain=float(self.gain)
        chunk_size=1024
        try:
            self.sdr = SoapySDR.Device(device_args)
        except Exception as e:
            print("HackRF not found!")
            print(e)
            self.stop_event()
            return
        self.sdr.setSampleRate(SoapySDR.SOAPY_SDR_TX, 0, sample_rate)
        self.sdr.setFrequency(SoapySDR.SOAPY_SDR_TX, 0, center_freq)
        self.sdr.setGain(SoapySDR.SOAPY_SDR_TX, 0, 'AMP', 1)
        self.sdr.setGain(SoapySDR.SOAPY_SDR_TX, 0, 'VGA', gain)

        tx_stream = self.sdr.setupStream(SoapySDR.SOAPY_SDR_TX, SoapySDR.SOAPY_SDR_CS8)
        
        self.sdr.activateStream(tx_stream)

        try:
            dtype = np.dtype([('re', np.int8), ('im', np.int8)])
    
            with open(file_path, 'rb') as f:
                while True:
                    iq_chunk = np.frombuffer(f.read(chunk_size * dtype.itemsize), dtype=dtype)
            
                    if len(iq_chunk) == 0:
                        
                        break  # Exit the loop if no more data is available

                    sr = self.sdr.writeStream(tx_stream, [iq_chunk], len(iq_chunk))
            
                    #print(sr.ret)
    
            print("EOF")

        except Exception as e:
            print(e)
            #self.stop_event()

        finally:
            self.sdr.deactivateStream(tx_stream)
            self.sdr.closeStream(tx_stream)
            print("SDR closed")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    dynamicdefaults = {}
    staticparameters = {'-e': ['plik efemerydy (statyczny)', 'brdc.n'], '-f': ['Częstotliwość fali nośnej', 1575420000], '-s': ['Częstotliwość próbkowania', 3000000],'-a': ['Wzmacniacz +11dB włączony 0 lub 1', 1]}

    window = ParameterPrinter(dynamicdefaults, staticparameters, 'fifo', 'fifocsv')
    window.show()

    sys.exit(app.exec())
