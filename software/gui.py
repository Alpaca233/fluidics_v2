import sys
import csv
import json
import time
import threading
import argparse
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QCheckBox, QFileDialog, QMessageBox, QComboBox,
                             QStyledItemDelegate, QSpinBox, QLabel, QProgressBar, QLineEdit, 
                             QGroupBox, QGridLayout, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot, Q_ARG, QMetaObject, QEvent, QCoreApplication
from PyQt5.QtGui import QColor

from control.controller import FluidController, FluidControllerSimulation
from control.syringe_pump import SyringePump, SyringePumpSimulation
from control.selector_valve import SelectorValveSystem
from control.disc_pump import DiscPump
from control.temperature_controller import TCMController, TCMControllerSimulation

from control._def import CMD_SET
from control.tecancavro.tecanapi import TecanAPITimeout
from merfish_operations import MERFISHOperations
from open_chamber_operations import OpenChamberOperations
from experiment_worker import ExperimentWorker

import pandas as pd


def load_config(config_path='./config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)


class SpinBoxDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QSpinBox(parent)
        editor.setMinimum(0)
        editor.setMaximum(10000)  # Set a reasonable maximum
        editor.setSingleStep(1)
        editor.setButtonSymbols(QSpinBox.UpDownArrows)  # Show up/down arrows by default
        return editor

    def setEditorData(self, spinBox, index):
        value = index.model().data(index, Qt.EditRole)
        spinBox.setValue(int(value))

    def setModelData(self, spinBox, model, index):
        spinBox.interpretText()
        value = spinBox.value()
        model.setData(index, value, Qt.EditRole)

    def paint(self, painter, option, index):
        # This ensures the spinbox is always visible
        if not self.parent().indexWidget(index):
            spinBox = QSpinBox(self.parent(), minimum=0, maximum=10000, singleStep=1)
            spinBox.setValue(int(index.data()))
            spinBox.valueChanged.connect(lambda value: self.parent().model().setData(index, value, Qt.EditRole))
            self.parent().setIndexWidget(index, spinBox)


class PortDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, ports=[]):
        super().__init__(parent)
        self.ports = ports

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self.ports)
        return editor

    def setEditorData(self, comboBox, index):
        value = index.model().data(index, Qt.EditRole)
        comboBox.setCurrentText(value)

    def setModelData(self, comboBox, model, index):
        value = int(comboBox.currentText())
        model.setData(index, value, Qt.EditRole)

    def paint(self, painter, option, index):
        if not self.parent().indexWidget(index):
            comboBox = QComboBox(self.parent())
            comboBox.addItems(map(str, self.ports))
            comboBox.setCurrentText(str(index.data()))
            comboBox.currentTextChanged.connect(lambda text: self.parent().model().setData(index, text, Qt.EditRole))
            self.parent().setIndexWidget(index, comboBox)


class WorkerEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, callback_name, *args):
        super().__init__(WorkerEvent.EVENT_TYPE)
        self.callback_name = callback_name
        self.args = args


class SequencesWidget(QWidget):
    def __init__(self, config, syringe, selector_valves, disc_pump, temperature_controller):
        super().__init__()
        self.config = config
        self.syringePump = syringe
        self.selectorValveSystem = selector_valves
        self.discPump = disc_pump
        self.temperatureController = temperature_controller

        self.sequences = pd.DataFrame()
        self.experiment_ops = None  # Will be set based on the selected application
        self.worker = None

        if self.config['application'] == 'MERFISH':
            self.experiment_ops = MERFISHOperations(self.config, self.syringePump, self.selectorValveSystem)
        elif self.config['application'] == "Open Chamber":
            self.experiment_ops = OpenChamberOperations(self.config, self.syringePump, self.selectorValveSystem, self.discPump, self.temperatureController)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Table for displaying sequences
        # TODO: use YAML for sequences
        self.table = QTableWidget()
        self.setupTable()
        layout.addWidget(self.table)

        # Buttons
        buttonLayout = QHBoxLayout()
        self.loadButton = QPushButton("Load CSV")
        self.loadButton.clicked.connect(self.loadCSV)
        self.saveButton = QPushButton("Save CSV")
        self.saveButton.clicked.connect(self.saveCSV)
        self.selectAllButton = QPushButton("Select All")
        self.selectAllButton.clicked.connect(self.selectAll)
        self.selectNoneButton = QPushButton("Select None")
        self.selectNoneButton.clicked.connect(self.selectNone)
        self.runButton = QPushButton("Run Selected Sequences")
        self.runButton.clicked.connect(self.runSelectedSequences)
        self.abortButton = QPushButton("Abort")
        self.abortButton.clicked.connect(self.abortSequences)
        self.abortButton.setEnabled(False)  # Initially disabled

        buttonLayout.addWidget(self.loadButton)
        buttonLayout.addWidget(self.saveButton)
        buttonLayout.addWidget(self.selectAllButton)
        buttonLayout.addWidget(self.selectNoneButton)
        buttonLayout.addWidget(self.runButton)
        buttonLayout.addWidget(self.abortButton)

        layout.addLayout(buttonLayout)

        # Progress bar
        self.progressBar = QProgressBar()
        self.sequenceLabel = QLabel("0/0 sequences")
        self.timeLabel = QLabel("00:00:00 remaining")

        progressSection = QVBoxLayout()
        progressLabelLayout = QHBoxLayout()
        progressLabelLayout.addWidget(self.sequenceLabel)
        progressLabelLayout.addStretch()
        progressLabelLayout.addWidget(self.timeLabel)
        progressSection.addLayout(progressLabelLayout)
        progressSection.addWidget(self.progressBar)

        layout.addLayout(progressSection)

        self.setLayout(layout)

        # Timer for updating time remaining
        self.timer = QTimer()
        self.timer.timeout.connect(self.updateTimeRemaining)
        self.elapsed_time = 0
        self.total_time = None

    def setupTable(self):
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["Sequence Name", "Fluidic Port", "Flow Rate (μL/min)", 
                                              "Volume (μL)", "Incubation Time (min)", "Repeat", "Fill Tubing With", "Include"])
        # Set up delegates
        spinBoxDelegate = SpinBoxDelegate(self.table)
        self.table.setItemDelegateForColumn(2, spinBoxDelegate)  # Flow Rate
        self.table.setItemDelegateForColumn(3, spinBoxDelegate)  # Volume
        self.table.setItemDelegateForColumn(4, spinBoxDelegate)  # Incubation Time
        self.table.setItemDelegateForColumn(5, spinBoxDelegate)  # Repeat
        self.table.setItemDelegateForColumn(6, spinBoxDelegate)  # Fill Tubing With

        # Set up port delegate with simplified port numbers
        ports = self.selectorValveSystem.get_port_names()
        self.portDelegate = PortDelegate(self.table, ports)
        self.table.setItemDelegateForColumn(1, self.portDelegate)  # Fluidic Port

        self.table.setStyleSheet("QHeaderView::section { padding-left: 5px; padding-right: 5px; }")
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def loadCSV(self):
        # Todo: use same load/save csv and runSelectedSequences for different applications
        fileName, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
        if fileName:
            try:
                # Read CSV into DataFrame
                self.sequences = pd.read_csv(fileName, dtype={
                    'sequence_name': str,
                    'fluidic_port': int,
                    'flow_rate': int,
                    'volume': int,
                    'incubation_time': int,
                    'repeat': int,
                    'fill_tubing_with': int,
                    'include': int
                })

                # Update table
                self.table.setRowCount(0)
                for idx, row in self.sequences.iterrows():
                    rowPosition = self.table.rowCount()
                    self.table.insertRow(rowPosition)

                    # Set items
                    self.table.setItem(rowPosition, 0, QTableWidgetItem(row['sequence_name']))
                    self.table.setItem(rowPosition, 1, QTableWidgetItem(self.portDelegate.ports[row['fluidic_port'] - 1]))
                    self.table.setItem(rowPosition, 2, QTableWidgetItem(str(row['flow_rate'])))
                    self.table.setItem(rowPosition, 3, QTableWidgetItem(str(row['volume'])))
                    self.table.setItem(rowPosition, 4, QTableWidgetItem(str(row['incubation_time'])))
                    self.table.setItem(rowPosition, 5, QTableWidgetItem(str(row['repeat'])))
                    self.table.setItem(rowPosition, 6, QTableWidgetItem(str(row['fill_tubing_with'])))

                    # Set checkbox
                    checkbox = QCheckBox()
                    checkbox.setChecked(row['include'] == 1)
                    self.table.setCellWidget(rowPosition, 7, checkbox)

                    # Make sequence name non-editable
                    self.table.item(rowPosition, 0).setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load CSV: {str(e)}")
                return

    def saveCSV(self):
        fileName, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if fileName:
            if not fileName.lower().endswith('.csv'):
                fileName += '.csv'
            try:
                # Update sequences from current table state and save
                self.getSequencesDF(False).to_csv(fileName, index=False)
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save CSV: {str(e)}")
                return

    def getSequencesDF(self, selected_only=False):
        # Create DataFrame from current table state
        data = []
        for row in range(self.table.rowCount()):
            row_data = {
                'sequence_name': self.table.item(row, 0).text(),
                'fluidic_port': (self.table.cellWidget(row, 1).currentIndex() + 1),
                'flow_rate': float(self.table.item(row, 2).text()),
                'volume': float(self.table.item(row, 3).text()),
                'incubation_time': int(self.table.item(row, 4).text()),
                'repeat': int(self.table.item(row, 5).text()),
                'fill_tubing_with': int(self.table.item(row, 6).text()),
                'include': 1 if self.table.cellWidget(row, 7).isChecked() else 0
            }
            data.append(row_data)
        
        # Update stored sequences
        self.sequences = pd.DataFrame(data)

        # Return selected sequences or all sequences
        if selected_only:
            return self.sequences[self.sequences['include'] == 1].copy()
        return self.sequences.copy()
        
    def selectAll(self):
        for row in range(self.table.rowCount()):
            self.table.cellWidget(row, 7).setChecked(True)

    def selectNone(self):
        for row in range(self.table.rowCount()):
            self.table.cellWidget(row, 7).setChecked(False)

    def highlightRow(self, row_index):
        """Highlight the currently running sequence"""
        # Reset all row highlights
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(QColor('white'))
        
        # Set new highlighting
        if row_index is not None:
            for col in range(self.table.columnCount()):
                item = self.table.item(row_index, col)
                if item:
                    item.setBackground(QColor('lightblue'))

    def runSelectedSequences(self):
        # TODO: map speed codes
        selected_sequences = self.getSequencesDF(True)
        self.total_sequences = selected_sequences['repeat'].sum()

        if selected_sequences.empty:
            QMessageBox.warning(self, "No Sequences Selected", "Please select at least one sequence to run.")
            return

        callbacks = {
            'update_progress': self.updateProgress,
            'on_error': self.handleError,
            'on_finished': self.onWorkerFinished,
            'on_estimate': self.setTimeEstimate
        }

        self.runButton.setEnabled(False)
        self.abortButton.setEnabled(True)

        self.worker = ExperimentWorker(self.experiment_ops, selected_sequences, self.config, callbacks)
        self.worker_thread = threading.Thread(target=self.worker.run, daemon=True)

        self.sequenceLabel.setText(f"0/{self.total_sequences} sequences")
        self.timer.start(1000)

        self.worker_thread.start()

    def updateTimeRemaining(self):
        """Update the time remaining display and progress bar"""
        self.elapsed_time += 1  # Add one second
        remaining = max(0, self.total_time - self.elapsed_time)

        # Update time label
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        seconds = int(remaining % 60)
        self.timeLabel.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d} remaining")
            
        # Update progress bar percentage
        progress = min(100, int((self.elapsed_time / self.total_time) * 100))
        self.progressBar.setValue(progress)
            
        if remaining <= 0:
            self.timer.stop()

    def event(self, event):
        if event.type() == WorkerEvent.EVENT_TYPE:
            if event.callback_name == 'update_progress':
                self._handle_progress(*event.args)
            elif event.callback_name == 'show_error':
                self._handle_error(*event.args)
            elif event.callback_name == 'on_finished':
                self._handle_finished()
            elif event.callback_name == 'set_time_estimate':
                self._handle_time_estimate(*event.args)
            return True
        return super().event(event)

    def _post_event(self, callback_name, *args):
        QCoreApplication.postEvent(self, WorkerEvent(callback_name, *args))

    def _handle_progress(self, index, sequence_num, status):
        self.sequenceLabel.setText(f"{sequence_num}/{self.total_sequences} sequences")
        self.highlightRow(index)

    def _handle_error(self, error_message):
        QMessageBox.critical(self, "Error", error_message)

    def _handle_finished(self):
        self.runButton.setEnabled(True)
        self.abortButton.setEnabled(False)
        self.progressBar.setValue(0)
        self.timeLabel.setText("00:00:00 remaining")
        self.sequenceLabel.setText("0/0 sequences")
        self.timer.stop()
        self.highlightRow(None)
        
        if self.worker:
            self.worker_thread.join()
            self.worker = None
            
        QMessageBox.information(self, "Finished", "Sequence execution finished.")

    def _handle_time_estimate(self, time_to_finish, n_sequences):
        self.total_time = time_to_finish
        self.progressBar.setMaximum(100)  # For percentage
        self.progressBar.setValue(0)

    def setTimeEstimate(self, time_to_finish, n_sequences):
        self._post_event('set_time_estimate', time_to_finish, n_sequences)

    def updateProgress(self, index, sequence_num, status):
        self._post_event('update_progress', index, sequence_num, status)

    def handleError(self, error_message):
        self._post_event('show_error', error_message)

    def onWorkerFinished(self):
        self._post_event('on_finished')

    def abortSequences(self):
        if self.worker and self.experiment_ops:
            self.worker.abort()
            self.abortButton.setEnabled(False)


class ManualControlWidget(QWidget):
    def __init__(self, config, syringe, selector_valves, disc_pump):
        super().__init__()
        self.config = config
        self.syringePump = syringe
        self.selectorValveSystem = selector_valves
        self.disc_pump = disc_pump

        # Initialize timers
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.updateProgress)
        
        self.plunger_timer = QTimer(self)
        self.plunger_timer.timeout.connect(self.updatePlungerPosition)
        
        self.operation_start_time = None
        self.operation_duration = None

        self.initUI()

    def initUI(self):
        mainLayout = QVBoxLayout()
        mainLayout.setSpacing(10)

        # Selector Valve Control
        valveGroupBox = QGroupBox("Selector Valve Control")
        valveLayout = QHBoxLayout()
        valveLayout.setContentsMargins(5, 5, 5, 5)
        valveLayout.addWidget(QLabel("Source port:"))
        self.valveCombo = QComboBox()
        self.valveCombo.addItems(self.selectorValveSystem.get_port_names())
        self.valveCombo.currentIndexChanged.connect(self.openValve)
        valveLayout.addWidget(self.valveCombo)
        valveGroupBox.setLayout(valveLayout)
        mainLayout.addWidget(valveGroupBox)

        if self.config['application'] == "Open Chamber":
            pumpGroupBox = QGroupBox("Disc Pump Control")
            pumpLayout = QHBoxLayout()
            pumpLayout.setContentsMargins(5, 5, 5, 5)
            pumpLayout.addWidget(QLabel("Operation time:"))
            self.pumpInput = QLineEdit()
            pumpLayout.addWidget(self.pumpInput)
            pumpLayout.addWidget(QLabel("s"))
            self.pumpButton = QPushButton("Start")
            pumpLayout.addWidget(self.pumpButton)
            self.pumpButton.clicked.connect(self.startDiscPump)
            pumpGroupBox.setLayout(pumpLayout)
            mainLayout.addWidget(pumpGroupBox)

        # Syringe Pump Control
        syringeGroupBox = QGroupBox("Syringe Pump Control")
        syringeLayout = QVBoxLayout()
        syringeLayout.setContentsMargins(5, 5, 5, 5)
        syringeLayout.setSpacing(5)

        topLayout = QHBoxLayout()

        # Left side controls
        leftWidget = QWidget()
        leftLayout = QGridLayout(leftWidget)
        self.syringePortCombo = QComboBox()
        self.syringePortCombo.addItems(map(str, self.config['syringe_pump']['ports_allowed']))
        leftLayout.addWidget(QLabel("Port:"), 0, 0)
        leftLayout.addWidget(self.syringePortCombo, 0, 1)

        self.speedCombo = QComboBox()
        speed_code_limit = self.config['syringe_pump']['speed_code_limit']
        for code in range(speed_code_limit, len(self.syringePump.SPEED_SEC_MAPPING)):
            rate = self.syringePump.get_flow_rate(code)
            self.speedCombo.addItem(f"{rate} mL/min", code)
        self.speedCombo.setCurrentIndex(40 - self.config['syringe_pump']['speed_code_limit'])  # Set default to code 40
        leftLayout.addWidget(QLabel("Speed:"), 1, 0)
        leftLayout.addWidget(self.speedCombo, 1, 1)

        self.volumeSpinBox = QSpinBox()
        self.volumeSpinBox.setRange(1, self.config['syringe_pump']['volume_ul'])
        self.volumeSpinBox.setSuffix(" μL")
        leftLayout.addWidget(QLabel("Volume:"), 2, 0)
        leftLayout.addWidget(self.volumeSpinBox, 2, 1)

        actionLayout = QHBoxLayout()
        self.pushButton = QPushButton("Extract")
        self.pushButton.clicked.connect(lambda: self.operateSyringe("extract"))
        self.pullButton = QPushButton("Dispense")
        self.pullButton.clicked.connect(lambda: self.operateSyringe("dispense"))
        self.emptyButton = QPushButton("Empty to Waste")
        self.emptyButton.clicked.connect(lambda: self.operateSyringe("empty"))
        actionLayout.addWidget(self.pushButton)
        actionLayout.addWidget(self.pullButton)
        leftLayout.addLayout(actionLayout, 3, 0, 1, 2)
        leftLayout.addWidget(self.emptyButton)

        topLayout.addWidget(leftWidget, 3)

        # Right side - Plunger position
        # TODO: stop updating position when not on this tab
        rightWidget = QWidget()
        rightLayout = QVBoxLayout(rightWidget)
        self.plungerPositionLabel = QLabel("Plunger Position (μL)")
        rightLayout.addWidget(self.plungerPositionLabel, alignment=Qt.AlignHCenter)
        self.plungerPositionBar = QProgressBar()
        self.plungerPositionBar.setRange(0, self.config['syringe_pump']['volume_ul'])
        self.plungerPositionBar.setOrientation(Qt.Vertical)
        self.plungerPositionBar.setTextVisible(False)
        rightLayout.addWidget(self.plungerPositionBar, alignment=Qt.AlignHCenter)

        topLayout.addWidget(rightWidget, 1)

        syringeLayout.addLayout(topLayout)

        self.syringeProgressBar = QProgressBar()
        self.syringeProgressBar.setRange(0, 100)
        syringeLayout.addWidget(QLabel("Execution Progress:"))
        syringeLayout.addWidget(self.syringeProgressBar)

        syringeGroupBox.setLayout(syringeLayout)
        mainLayout.addWidget(syringeGroupBox)

        self.setLayout(mainLayout)

        # Initialize plunger position
        self.updatePlungerPosition()

    def openValve(self):
        port = self.valveCombo.currentIndex() + 1
        self.selectorValveSystem.open_port(port)

    def operateSyringe(self, action):
        if self.syringePump.is_busy:
            print("Syringe pump is busy.")
            return

        syringe_port = int(self.syringePortCombo.currentText())
        speed_code = self.speedCombo.currentData()
        volume = self.volumeSpinBox.value()
        
        try:
            # Disable control buttons during operation
            self.setControlsEnabled(False)

            # Start operation
            self.syringePump.reset_chain()
            if action == "dispense":
                exec_time = self.syringePump.dispense(syringe_port, volume, speed_code)
            elif action == "extract":
                exec_time = self.syringePump.extract(syringe_port, volume, speed_code)
            elif action == "empty":
                exec_time = self.syringePump.dispense_to_waste()

            # Set up progress tracking
            self.operation_duration = exec_time

            # Start syringe operation in a separate thread
            operation_thread = threading.Thread(target=self._executeSyringeOperation, 
                                             args=(action, syringe_port, volume, speed_code))
            operation_thread.daemon = True
            operation_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error operating syringe pump: {str(e)}")
            self.setControlsEnabled(True)

    def _executeSyringeOperation(self, action, syringe_port, volume, speed_code):
        try:
            self.operation_start_time = time.time()

            # Start progress updates
            QMetaObject.invokeMethod(self, "startProgressTimer", Qt.QueuedConnection)

            self.syringePump.execute()

            # Clean up
            QMetaObject.invokeMethod(self, "operationComplete", Qt.QueuedConnection)

        except TecanAPITimeout:
            QMetaObject.invokeMethod(self, "operationComplete", Qt.QueuedConnection)

        except Exception as e:
            QMetaObject.invokeMethod(self, "handleError", 
                                   Qt.QueuedConnection,
                                   Q_ARG(str, str(e)))

    def startDiscPump(self):
        if self.disc_pump is not None:
            self.pumpButton.setEnabled(False)
            self.disc_pump.aspirate(float(self.pumpInput.text()))
            self.pumpButton.setEnabled(True)

    @pyqtSlot()
    def startProgressTimer(self):
        self.syringeProgressBar.setValue(0)
        self.progress_timer.start(100)  # Update progress every 100ms

    @pyqtSlot()
    def operationComplete(self):
        self.progress_timer.stop()
        self.syringeProgressBar.setValue(100)
        self.setControlsEnabled(True)
        self.operation_start_time = None
        self.operation_duration = None
        self.syringePump.is_busy = False

    @pyqtSlot(str)
    def handleError(self, error_message):
        #if error_message[:48] != "Tecan serial communication exceeded max attempts":
        QMessageBox.critical(self, "Error", f"Syringe pump error: {error_message}")
        self.syringePump.wait_for_stop()
        self.setControlsEnabled(True)
        self.progress_timer.stop()
        self.syringeProgressBar.setValue(0)

    def setControlsEnabled(self, enabled):
        self.pushButton.setEnabled(enabled)
        self.pullButton.setEnabled(enabled)
        self.emptyButton.setEnabled(enabled)
        self.syringePortCombo.setEnabled(enabled)
        self.speedCombo.setEnabled(enabled)
        self.volumeSpinBox.setEnabled(enabled)

    def updateProgress(self):
        if self.operation_start_time is None or self.operation_duration is None:
            return
            
        elapsed = time.time() - self.operation_start_time
        progress = min(100, int((elapsed / self.operation_duration) * 100))
        self.syringeProgressBar.setValue(progress)

    def updatePlungerPosition(self):
        try:
            position = self.syringePump.get_plunger_position() * self.config['syringe_pump']['volume_ul']
            self.plungerPositionBar.setValue(int(position))
        except Exception:
            pass

    def showEvent(self, event):
        # Start timer when widget becomes visible
        super().showEvent(event)
        self.plunger_timer.start(500)
        self.valveCombo.setCurrentIndex(self.selectorValveSystem.get_current_port() - 1)

    def hideEvent(self, event):
        # Stop timer when widget becomes hidden
        super().hideEvent(event)
        self.plunger_timer.stop()

    def closeEvent(self, event):
        self.progress_timer.stop()
        self.position_timer.stop()
        super().closeEvent(event)


class FluidicsControlGUI(QMainWindow):
    def __init__(self, is_simulation):
        super().__init__()
        self.config = load_config()
        self.simulation = is_simulation
        self.temperatureController = None

        self.initialize_hardware(self.simulation, self.config)
        self.selectorValveSystem = SelectorValveSystem(self.controller, self.config)

        if self.config['application'] == "Open Chamber":
            self.discPump = DiscPump(self.controller)
        else:
            self.discPump = None

        self.initUI()

    def initUI(self):
        self.setWindowTitle("Fluidics Control System")
        self.setGeometry(100, 100, 950, 600)

        # Create tab widget
        tabWidget = QTabWidget()

        # "Settings and Manual Control" tab
        runExperimentsTab = SequencesWidget(self.config, self.syringePump, self.selectorValveSystem, self.discPump, self.temperatureController)
        manualControlTab = ManualControlWidget(self.config, self.syringePump, self.selectorValveSystem, self.discPump)
        # TODO: integrate temperature controller ui

        tabWidget.addTab(runExperimentsTab, "Run Experiments")
        tabWidget.addTab(manualControlTab, "Settings and Manual Control")

        self.setCentralWidget(tabWidget)

    def initialize_hardware(self, simulation, config):
        if simulation:
            self.controller = FluidControllerSimulation(config['microcontroller']['serial_number'])
            self.syringePump = SyringePumpSimulation(
                                sn=config['syringe_pump']['serial_number'],
                                syringe_ul=config['syringe_pump']['volume_ul'], 
                                speed_code_limit=config['syringe_pump']['speed_code_limit'],
                                waste_port=3)
            if 'temperature_controller' in config and config['use_temperature_controller']:
                self.temperatureController = TCMControllerSimulation()
        else:
            self.controller = FluidController(config['microcontroller']['serial_number'])
            self.syringePump = SyringePump(
                                sn=config['syringe_pump']['serial_number'],
                                syringe_ul=config['syringe_pump']['volume_ul'], 
                                speed_code_limit=config['syringe_pump']['speed_code_limit'],
                                waste_port=3)
            if 'temperature_controller' in config and config['temperature_controller']['use_temperature_controller']:
                self.temperatureController = TCMController(config['temperature_controller']['serial_number'])

        self.controller.begin()
        self.controller.send_command(CMD_SET.CLEAR)

    def closeEvent(self, event):
        if self.config['application'] == "Open Chamber":
            self.syringePump.close()
        elif self.config['application'] == "MERFISH":
            self.syringePump.close(True)
        super().closeEvent(event)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation", help="Run the GUI with simulated hardware.", action='store_true')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    gui = FluidicsControlGUI(args.simulation)
    gui.show()
    sys.exit(app.exec_())
