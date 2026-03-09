import os
import sys
import csv
import json
import time
import threading
import argparse
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem,
                             QHeaderView, QCheckBox, QFileDialog, QMessageBox, QComboBox,
                             QSpinBox, QLabel, QProgressBar, QLineEdit,
                             QGroupBox, QGridLayout, QSizePolicy, QDialog, QFormLayout,
                             QDoubleSpinBox, QDialogButtonBox)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot, Q_ARG, QMetaObject, QEvent, QCoreApplication
from PyQt5.QtGui import QColor, QBrush

from fluidics.control.config import load_config
from fluidics.control.controller import FluidController, FluidControllerSimulation
from fluidics.control.syringe_pump import SyringePump, SyringePumpSimulation
from fluidics.control.selector_valve import SelectorValveSystem
from fluidics.control.disc_pump import DiscPump
from fluidics.control.temperature_controller import TCMController, TCMControllerSimulation

from fluidics.control._def import CMD_SET
from fluidics.control.tecancavro.tecanapi import TecanAPITimeout
from fluidics.merfish_operations import MERFISHOperations
from fluidics.open_chamber_operations import OpenChamberOperations
from fluidics.experiment_worker import ExperimentWorker
from fluidics.sequences import (
    load_sequences, save_sequences_yaml, get_included_sequences,
    get_fields_for_type, SEQUENCE_TYPES, SEQUENCE_TYPE_LABELS, APPLICATION_SEQUENCES
)

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import warnings
warnings.filterwarnings('ignore')

def load_config_file(config_path=None):
    if config_path is None:
        # Try YAML first, fall back to JSON (which auto-converts)
        if os.path.exists('./config.yaml'):
            config_path = './config.yaml'
        else:
            config_path = './config.json'
    return load_config(config_path)


class WorkerEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, callback_name, *args):
        super().__init__(WorkerEvent.EVENT_TYPE)
        self.callback_name = callback_name
        self.args = args


class AddSequenceDialog(QDialog):
    """Dialog for adding a new sequence to the tree."""

    def __init__(self, parent, application, port_names):
        super().__init__(parent)
        self.setWindowTitle("Add Sequence")
        self.application = application
        self.port_names = port_names
        self.result_dict = None
        self._field_widgets = {}

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Sequence type selector
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.typeCombo = QComboBox()
        available_types = APPLICATION_SEQUENCES.get(self.application, list(SEQUENCE_TYPES.keys()))
        for seq_type in available_types:
            self.typeCombo.addItem(SEQUENCE_TYPE_LABELS.get(seq_type, seq_type), seq_type)
        type_layout.addWidget(self.typeCombo)
        layout.addLayout(type_layout)

        # Form for fields
        self.formLayout = QFormLayout()
        layout.addLayout(self.formLayout)

        # OK/Cancel
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

        # Connect type change
        self.typeCombo.currentIndexChanged.connect(self._rebuild_fields)
        self._rebuild_fields()

    def _rebuild_fields(self):
        # Clear existing form rows
        while self.formLayout.rowCount() > 0:
            self.formLayout.removeRow(0)
        self._field_widgets.clear()

        seq_type = self.typeCombo.currentData()
        fields = get_fields_for_type(seq_type)

        for field_name, field_info in fields.items():
            if field_name == 'include':
                continue  # handled by tree checkbox

            default = field_info.default if field_info.default is not None else None

            if field_name == 'name':
                widget = QLineEdit()
                if default is not None:
                    widget.setText(str(default))
            elif field_name == 'fluidic_port':
                widget = QComboBox()
                for i, pname in enumerate(self.port_names):
                    widget.addItem(pname, i + 1)
                if default is not None:
                    widget.setCurrentIndex(max(0, int(default) - 1))
            elif field_name in ('temperature', 'incubation_time'):
                widget = QDoubleSpinBox()
                widget.setDecimals(2)
                widget.setRange(0, 100000)
                if default is not None:
                    widget.setValue(float(default))
            else:
                # int fields: flow_rate, volume, repeat, fill_tubing_with
                widget = QSpinBox()
                widget.setRange(0, 100000)
                if default is not None:
                    widget.setValue(int(default))

            self._field_widgets[field_name] = widget
            self.formLayout.addRow(field_name, widget)

    def accept(self):
        seq_type = self.typeCombo.currentData()
        d = {'type': seq_type}
        for field_name, widget in self._field_widgets.items():
            if isinstance(widget, QLineEdit):
                val = widget.text().strip()
                if val:
                    d[field_name] = val
            elif isinstance(widget, QComboBox):
                d[field_name] = widget.currentData()
            elif isinstance(widget, QDoubleSpinBox):
                d[field_name] = widget.value()
            elif isinstance(widget, QSpinBox):
                d[field_name] = widget.value()
        self.result_dict = d
        super().accept()


class SequencesWidget(QWidget):

    sequence_running = pyqtSignal(bool)

    def __init__(self, config, syringe, selector_valves, disc_pump, temperature_controller):
        super().__init__()
        self.config = config
        self.syringePump = syringe
        self.selectorValveSystem = selector_valves
        self.discPump = disc_pump
        self.temperatureController = temperature_controller

        self.experiment_ops = None  # Will be set based on the selected application
        self.worker = None

        if self.config.application == 'Flow Cell':
            self.experiment_ops = MERFISHOperations(self.config, self.syringePump, self.selectorValveSystem)
        elif self.config.application == "Open Chamber":
            self.experiment_ops = OpenChamberOperations(self.config, self.syringePump, self.selectorValveSystem, self.discPump, self.temperatureController)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Tree for displaying sequences
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Property", "Value"])
        self.tree.setColumnCount(2)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        layout.addWidget(self.tree)

        # Buttons
        buttonLayout = QHBoxLayout()
        self.loadButton = QPushButton("Load")
        self.loadButton.clicked.connect(self.loadSequences)
        self.saveButton = QPushButton("Save")
        self.saveButton.clicked.connect(self.saveSequences)
        self.addButton = QPushButton("Add Sequence")
        self.addButton.clicked.connect(self.addSequence)
        self.removeButton = QPushButton("Remove Sequence")
        self.removeButton.clicked.connect(self.removeSequence)
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
        buttonLayout.addWidget(self.addButton)
        buttonLayout.addWidget(self.removeButton)
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

    def _make_top_level_label(self, seq):
        """Build the display label for a top-level tree item."""
        seq_type = seq.get('type', '')
        label = SEQUENCE_TYPE_LABELS.get(seq_type, seq_type)
        name = seq.get('name')
        if name:
            label = f"{label} \u2014 {name}"
        return label

    def populateTree(self, sequences):
        """Populate the tree widget from a list of sequence dicts."""
        self.tree.clear()
        for seq in sequences:
            self._addSequenceItem(seq)

    def _addSequenceItem(self, seq):
        """Add a single sequence dict as a top-level tree item."""
        seq_type = seq.get('type', '')
        label = self._make_top_level_label(seq)

        item = QTreeWidgetItem([label, ''])
        item.setData(0, Qt.UserRole, seq_type)

        # Include checkbox
        include = seq.get('include', True)
        item.setCheckState(0, Qt.Checked if include else Qt.Unchecked)

        # Determine which fields to show
        try:
            type_fields = get_fields_for_type(seq_type)
        except ValueError:
            type_fields = {}

        # Required fields (no default or default is a required sentinel)
        required_field_names = set()
        for fname, finfo in type_fields.items():
            if fname in ('type', 'include'):
                continue
            if finfo.is_required():
                required_field_names.add(fname)

        # Add child items for fields (excluding 'type' and 'include')
        for fname, finfo in type_fields.items():
            if fname in ('type', 'include'):
                continue
            value = seq.get(fname)
            default = finfo.default

            # Show field if it has a non-None, non-default value, or is required
            if fname in required_field_names or (value is not None and value != default):
                display_value = str(value) if value is not None else ''
                child = QTreeWidgetItem([fname, display_value])
                child.setFlags(child.flags() | Qt.ItemIsEditable)
                item.addChild(child)

        self.tree.addTopLevelItem(item)
        item.setExpanded(True)

    def getSequences(self, selected_only=False):
        """Read the tree back into a list of sequence dicts."""
        sequences = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            seq_type = item.data(0, Qt.UserRole)
            include = item.checkState(0) == Qt.Checked

            if selected_only and not include:
                continue

            seq = {'type': seq_type, 'include': include}

            for j in range(item.childCount()):
                child = item.child(j)
                fname = child.text(0)
                raw_value = child.text(1).strip()

                if not raw_value:
                    continue

                # Type conversion
                if fname in ('fluidic_port', 'flow_rate', 'volume', 'repeat', 'fill_tubing_with'):
                    try:
                        seq[fname] = int(raw_value)
                    except ValueError:
                        seq[fname] = raw_value
                elif fname in ('temperature', 'incubation_time'):
                    try:
                        seq[fname] = float(raw_value)
                    except ValueError:
                        seq[fname] = raw_value
                else:
                    seq[fname] = raw_value

            sequences.append(seq)
        return sequences

    def loadSequences(self):
        fileName, _ = QFileDialog.getOpenFileName(
            self, "Open Sequences", "",
            "Sequence Files (*.yaml *.yml *.csv)")
        if fileName:
            try:
                sequences = load_sequences(fileName)
                self.populateTree(sequences)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load sequences: {str(e)}")

    def saveSequences(self):
        fileName, _ = QFileDialog.getSaveFileName(
            self, "Save Sequences", "",
            "YAML Files (*.yaml)")
        if fileName:
            if not fileName.lower().endswith(('.yaml', '.yml')):
                fileName += '.yaml'
            try:
                save_sequences_yaml(self.getSequences(), fileName)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save sequences: {str(e)}")

    def addSequence(self):
        port_names = self.selectorValveSystem.get_port_names()
        dialog = AddSequenceDialog(self, self.config.application, port_names)
        if dialog.exec_() == QDialog.Accepted and dialog.result_dict:
            self._addSequenceItem(dialog.result_dict)

    def removeSequence(self):
        current = self.tree.currentItem()
        if current is None:
            return
        # If a child is selected, remove its parent (the top-level sequence)
        if current.parent() is not None:
            current = current.parent()
        index = self.tree.indexOfTopLevelItem(current)
        if index >= 0:
            self.tree.takeTopLevelItem(index)

    def selectAll(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Checked)

    def selectNone(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Unchecked)

    def highlightRow(self, row_index):
        """Highlight the currently running sequence in the tree."""
        white_brush = QBrush(QColor('white'))
        blue_brush = QBrush(QColor('lightblue'))

        # Reset all highlights
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setBackground(0, white_brush)
            item.setBackground(1, white_brush)

        # Set new highlighting
        if row_index is not None and row_index < self.tree.topLevelItemCount():
            item = self.tree.topLevelItem(row_index)
            item.setBackground(0, blue_brush)
            item.setBackground(1, blue_brush)

    def runSelectedSequences(self):
        if self.tree.topLevelItemCount() == 0:
            return
        selected = self.getSequences(selected_only=True)
        self.total_sequences = sum(s.get('repeat', 1) for s in selected)

        if not selected:
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
        self.sequence_running.emit(True)

        self.worker = ExperimentWorker(self.experiment_ops, selected, self.config, callbacks)
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
        self.sequence_running.emit(False)
        
        if self.worker:
            self.worker_thread.join()
            self.worker = None

        self.syringePump.reset_abort()
        if self.temperatureController is not None:
            self.temperatureController.reset_abort()
        if self.discPump is not None:
            self.discPump.reset_abort()
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
            self.syringePump.abort()
            if self.discPump is not None:
                self.discPump.abort()
            if self.temperatureController is not None:
                self.temperatureController.abort()
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

        if self.config.application == "Open Chamber":
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
        self.syringePortCombo.addItems(map(str, self.config.syringe_pump.ports_allowed))
        leftLayout.addWidget(QLabel("Port:"), 0, 0)
        leftLayout.addWidget(self.syringePortCombo, 0, 1)

        self.speedCombo = QComboBox()
        speed_code_limit = self.config.syringe_pump.speed_code_limit
        for code in range(speed_code_limit, len(self.syringePump.SPEED_SEC_MAPPING)):
            rate = self.syringePump.get_flow_rate(code)
            self.speedCombo.addItem(f"{rate} mL/min", code)
        self.speedCombo.setCurrentIndex(40 - self.config.syringe_pump.speed_code_limit)  # Set default to code 40
        leftLayout.addWidget(QLabel("Speed:"), 1, 0)
        leftLayout.addWidget(self.speedCombo, 1, 1)

        self.volumeSpinBox = QSpinBox()
        self.volumeSpinBox.setRange(1, self.config.syringe_pump.volume_ul)
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
        self.plungerPositionBar.setRange(0, self.config.syringe_pump.volume_ul)
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
            position = self.syringePump.get_plunger_position() * self.config.syringe_pump.volume_ul
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


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)


class TemperatureControlWidget(QWidget):

    temperature_update_signal = pyqtSignal(float, float)

    def __init__(self, temperature_controller):
        super().__init__()
        self.temperatureController = temperature_controller
        
        # Setup data
        self.temps1 = []
        self.temps2 = []
        self.times = []
        self.targets1 = []
        self.targets2 = []

        # Setup intervals and windows
        self.query_interval1 = 2
        self.query_interval2 = 2
        self.window_size1 = 60
        self.window_size2 = 60
        self.last_update1 = 0
        self.last_update2 = 0

        # Create update signal to handle thread safety
        self.temperature_update_signal.connect(self.handle_temperature_update)

        # Set the temperature callback to emit signal
        self.temperatureController.temperature_updating_callback = self.temperature_callback

        # Setup UI
        self.initUI()

        self.temp_input1.setText(f"{self.temperatureController.target_temperature_ch1:.2f}")
        self.temp_input2.setText(f"{self.temperatureController.target_temperature_ch2:.2f}")
        self.temperatureController.actual_temp_updating_thread.start()

    def create_plot_controls(self, channel):
        control_widget = QWidget()
        layout = QHBoxLayout(control_widget)

        # Query interval control
        layout.addWidget(QLabel("Query Interval:"))
        interval_input = QSpinBox()
        interval_input.setMinimum(2)
        interval_input.setValue(2)
        interval_input.setSuffix(" s")
        layout.addWidget(interval_input)

        # Window size control
        layout.addWidget(QLabel("Window Size:"))
        window_input = QSpinBox()
        window_input.setMinimum(10)
        window_input.setMaximum(3600)  # 1 hour maximum
        window_input.setValue(60)
        window_input.setSuffix(" s")
        layout.addWidget(window_input)

        # Connect signals
        if channel == 1:
            interval_input.valueChanged.connect(self.set_interval1)
            window_input.valueChanged.connect(self.set_window1)
            self.interval_input1 = interval_input
            self.window_input1 = window_input
        else:
            interval_input.valueChanged.connect(self.set_interval2)
            window_input.valueChanged.connect(self.set_window2)
            self.interval_input2 = interval_input
            self.window_input2 = window_input

        return control_widget

    def initUI(self):
        main_layout = QVBoxLayout(self)

        # Create top section for temperature controls
        temp_controls = QWidget()
        temp_controls_layout = QHBoxLayout(temp_controls)

        # Channel 1 Controls
        ch1_control = QGroupBox("Channel 1 Control")
        ch1_control_layout = QVBoxLayout()

        temp_layout1 = QHBoxLayout()
        self.temp_label1 = QLabel("0.0°C")
        self.temp_input1 = QLineEdit()
        self.set_btn1 = QPushButton("Set")
        self.save_btn1 = QPushButton("Save")
        temp_layout1.addWidget(QLabel("Current:"))
        temp_layout1.addWidget(self.temp_label1)
        temp_layout1.addWidget(QLabel("Target:"))
        temp_layout1.addWidget(self.temp_input1)
        temp_layout1.addWidget(QLabel("°C"))
        temp_layout1.addWidget(self.set_btn1)
        temp_layout1.addWidget(self.save_btn1)

        ch1_control_layout.addLayout(temp_layout1)
        ch1_control.setLayout(ch1_control_layout)

        # Channel 2 Controls
        ch2_control = QGroupBox("Channel 2 Control")
        ch2_control_layout = QVBoxLayout()

        temp_layout2 = QHBoxLayout()
        self.temp_label2 = QLabel("0.0°C")
        self.temp_input2 = QLineEdit()
        self.set_btn2 = QPushButton("Set")
        self.save_btn2 = QPushButton("Save")
        temp_layout2.addWidget(QLabel("Current:"))
        temp_layout2.addWidget(self.temp_label2)
        temp_layout2.addWidget(QLabel("Target:"))
        temp_layout2.addWidget(self.temp_input2)
        temp_layout2.addWidget(QLabel("°C"))
        temp_layout2.addWidget(self.set_btn2)
        temp_layout2.addWidget(self.save_btn2)

        ch2_control_layout.addLayout(temp_layout2)
        ch2_control.setLayout(ch2_control_layout)

        # Add controls to top section
        temp_controls_layout.addWidget(ch1_control)
        temp_controls_layout.addWidget(ch2_control)

        # Add top section to main layout
        main_layout.addWidget(temp_controls)

        # Create plots section
        plots = QWidget()
        plots_layout = QHBoxLayout(plots)

        # Channel 1 Plot
        ch1_plot = QGroupBox("Channel 1 Plot")
        ch1_plot_layout = QVBoxLayout()

        # Add plot controls
        ch1_plot_layout.addWidget(self.create_plot_controls(1))

        self.canvas1 = MplCanvas(self, width=5, height=4, dpi=100)
        self.record_btn1 = QPushButton("Start Recording")

        ch1_plot_layout.addWidget(self.canvas1)
        ch1_plot_layout.addWidget(self.record_btn1)
        ch1_plot.setLayout(ch1_plot_layout)

        # Channel 2 Plot
        ch2_plot = QGroupBox("Channel 2 Plot")
        ch2_plot_layout = QVBoxLayout()

        # Add plot controls
        ch2_plot_layout.addWidget(self.create_plot_controls(2))

        self.canvas2 = MplCanvas(self, width=5, height=4, dpi=100)
        self.record_btn2 = QPushButton("Start Recording")

        ch2_plot_layout.addWidget(self.canvas2)
        ch2_plot_layout.addWidget(self.record_btn2)
        ch2_plot.setLayout(ch2_plot_layout)

        # Add plots to plots section
        plots_layout.addWidget(ch1_plot)
        plots_layout.addWidget(ch2_plot)

        # Add plots section to main layout
        main_layout.addWidget(plots)

        # Connect signals
        self.set_btn1.clicked.connect(lambda: self.set_temp(1))
        self.set_btn2.clicked.connect(lambda: self.set_temp(2))
        self.save_btn1.clicked.connect(lambda: self.save_temp(1))
        self.save_btn2.clicked.connect(lambda: self.save_temp(2))
        self.record_btn1.clicked.connect(lambda: self.toggle_record(1))
        self.record_btn2.clicked.connect(lambda: self.toggle_record(2))

    def set_interval1(self, value):
        self.query_interval1 = value

    def set_interval2(self, value):
        self.query_interval2 = value

    def set_window1(self, value):
        self.window_size1 = value
        self._update_plot(self.canvas1, self.temps1, self.targets1, 1)

    def set_window2(self, value):
        self.window_size2 = value
        self._update_plot(self.canvas2, self.temps2, self.targets2, 2)

    def handle_temperature_update(self, temp1, temp2):
        current_time = datetime.now().timestamp()

        # Update Channel 1
        if current_time - self.last_update1 >= self.query_interval1:
            self.temp_label1.setText(f"{temp1:.1f}°C")
            self.temps1.append(temp1)
            self.targets1.append(self.temperatureController.target_temperature_ch1)
            self.times.append(current_time)

            # Write to CSV if recording
            if hasattr(self, 'writer1') and self.record_btn1.text() == "Stop Recording":
                target = self.temperatureController.target_temperature_ch1
                self.writer1.writerow([datetime.fromtimestamp(current_time), temp1, target])

            self._update_plot(self.canvas1, self.temps1, self.targets1, 1)
            self.last_update1 = current_time

        # Update Channel 2
        if current_time - self.last_update2 >= self.query_interval2:
            self.temp_label2.setText(f"{temp2:.1f}°C")
            self.temps2.append(temp2)
            self.targets2.append(self.temperatureController.target_temperature_ch2)

            # Write to CSV if recording
            if hasattr(self, 'writer2') and self.record_btn2.text() == "Stop Recording":
                target = self.temperatureController.target_temperature_ch2
                self.writer2.writerow([datetime.fromtimestamp(current_time), temp2, target])

            self._update_plot(self.canvas2, self.temps2, self.targets2, 2)
            self.last_update2 = current_time

        # Cleanup old data
        while self.times and current_time - self.times[0] > max(self.window_size1, self.window_size2):
            self.times.pop(0)
            if self.temps1: self.temps1.pop(0)
            if self.temps2: self.temps2.pop(0)
            if self.targets1: self.targets1.pop(0)
            if self.targets2: self.targets2.pop(0)

    def _update_plot(self, canvas, temps, targets, channel):
        if not temps or not self.times:
            return

        canvas.axes.clear()

        # Plot the data
        canvas.axes.plot(self.times, temps, 'b-', label='Actual')
        canvas.axes.plot(self.times, targets, 'r--', label='Target')

        # Set y-axis limits with padding
        y_min = min(min(temps), min(targets))
        y_max = max(max(temps), max(targets))
        padding = (y_max - y_min) * 0.1 if y_max != y_min else 1.0
        canvas.axes.set_ylim([y_min - padding, y_max + padding])

        # Set x-axis to show window size
        window_size = self.window_size1 if channel == 1 else self.window_size2
        current_time = self.times[-1]
        canvas.axes.set_xlim([current_time - window_size, current_time])

        # Format time axis
        canvas.axes.set_xlabel('Seconds Ago')
        canvas.axes.set_ylabel('Temperature (°C)')
        canvas.axes.set_title(f'Channel {channel} Temperature')
        canvas.axes.grid(True)
        canvas.axes.legend()

        # Convert timestamps to relative time for display
        canvas.axes.set_xticklabels([f"{x:.0f}" for x in current_time - canvas.axes.get_xticks()])

        canvas.draw()

    def set_temp(self, channel):
        temp_input = self.temp_input1 if channel == 1 else self.temp_input2
        try:
            temp = float(temp_input.text())
            self.temperatureController.set_target_temperature(f'TC{channel}', temp)
        except ValueError:
            print(f"Invalid temperature for channel {channel}")

    def save_temp(self, channel):
        self.temperatureController.save_target_temperature(f'TC{channel}')

    def toggle_record(self, channel):
        btn = self.record_btn1 if channel == 1 else self.record_btn2
        if btn.text() == "Start Recording":
            btn.setText("Stop Recording")
            filename = f"temp_ch{channel}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            if channel == 1:
                self.file1 = open(filename, 'w', newline='')
                self.writer1 = csv.writer(self.file1)
                self.writer1.writerow(['Time', 'Actual Temperature', 'Target Temperature'])
            else:
                self.file2 = open(filename, 'w', newline='')
                self.writer2 = csv.writer(self.file2)
                self.writer2.writerow(['Time', 'Actual Temperature', 'Target Temperature'])
        else:
            btn.setText("Start Recording")
            if channel == 1:
                self.file1.close()
            else:
                self.file2.close()

    def temperature_callback(self, temp1, temp2):
        # This runs in the controller thread, emit signal to handle in GUI thread
        self.temperature_update_signal.emit(temp1, temp2)

    def closeEvent(self, event):
        # Close any open files
        if hasattr(self, 'file1') and self.file1:
            self.file1.close()
        if hasattr(self, 'file2') and self.file2:
            self.file2.close()
        event.accept()


class FluidicsControlGUI(QMainWindow):
    def __init__(self, is_simulation):
        super().__init__()
        self.config = load_config_file()
        self.simulation = is_simulation
        self.temperatureController = None

        self.initialize_hardware(self.simulation, self.config)
        self.selectorValveSystem = SelectorValveSystem(self.controller, self.config)

        if self.config.application == "Open Chamber":
            self.discPump = DiscPump(self.controller)
        else:
            self.discPump = None

        self.initUI()

    def initUI(self):
        self.setWindowTitle("Fluidics Control System")
        self.setGeometry(100, 100, 950, 600)

        # Create tab widget
        self.tabWidget = QTabWidget()

        # "Settings and Manual Control" tab
        runExperimentsTab = SequencesWidget(self.config, self.syringePump, self.selectorValveSystem, self.discPump, self.temperatureController)
        manualControlTab = ManualControlWidget(self.config, self.syringePump, self.selectorValveSystem, self.discPump)
        # TODO: integrate temperature controller ui

        self.tabWidget.addTab(runExperimentsTab, "Run Experiments")
        self.tabWidget.addTab(manualControlTab, "Settings and Manual Control")
        if self.temperatureController is not None:
            temperatureControlTab = TemperatureControlWidget(self.temperatureController)
            self.tabWidget.addTab(temperatureControlTab, "Temperature Control")

        self.setCentralWidget(self.tabWidget)
        runExperimentsTab.sequence_running.connect(self.set_manual_control_tab_state)

    def initialize_hardware(self, simulation, config):
        if simulation:
            self.controller = FluidControllerSimulation(config.microcontroller.serial_number)
            self.syringePump = SyringePumpSimulation(
                                sn=config.syringe_pump.serial_number,
                                syringe_ul=config.syringe_pump.volume_ul,
                                speed_code_limit=config.syringe_pump.speed_code_limit,
                                waste_port=config.syringe_pump.waste_port)
            if config.temperature_controller is not None:
                self.temperatureController = TCMControllerSimulation()
        else:
            self.controller = FluidController(config.microcontroller.serial_number)
            self.syringePump = SyringePump(
                                sn=config.syringe_pump.serial_number,
                                syringe_ul=config.syringe_pump.volume_ul,
                                speed_code_limit=config.syringe_pump.speed_code_limit,
                                waste_port=config.syringe_pump.waste_port)
            if config.temperature_controller is not None:
                try:
                    self.temperatureController = TCMController(config.temperature_controller.serial_number)
                except Exception as e:
                    print(f"Error initializing temperature controller: {e}")
                    self.temperatureController = None

        self.controller.begin()
        self.controller.send_command(CMD_SET.CLEAR)

    def set_manual_control_tab_state(self, is_running):
        manual_control_tab_index = 1
        self.tabWidget.setTabEnabled(manual_control_tab_index, not is_running)

    def closeEvent(self, event):
        if self.temperatureController is not None:
            self.temperatureController.terminate_temperature_updating_thread = True
            self.temperatureController.actual_temp_updating_thread.join()
            self.temperatureController.serial.close()

        if self.config.application == "Open Chamber":
            self.syringePump.close()
        elif self.config.application == "Flow Cell":
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
