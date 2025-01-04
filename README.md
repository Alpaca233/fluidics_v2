# Usage

### MERFISH
To run MERFISH sequences, load a .csv file and click 'Run Selected Sequences'. `merfish-experiment.csv` is an example.

After running the named operation, the syringe pump will extract liquid from the port in column 'fill_tubing_with' to fill the tubing. Setting the port value to '0' will disable this behavior.

Change configurations in `config.json` as needed. 
- "serial_number" of microcontroller and syringe pump: Connect one serial device at a time and run `list_controllers.py` to find out the serial number.
- "valve_ids_allowed": Connect the selector valves to the ports on the PCB. If there are three selector valves, connect them to port 0, 1 and 2 and set "valve_ids_allowed" to [0, 1, 2].
- "tubing_fluid_amount_ul": Fluid in the tubings that connect each selector valve. This will be used for calculate the amount of fluid extracted in 'fill_tubing_with'.
- "reagent_name_mapping": Show the reagent names of each port in the GUI (optional). 
