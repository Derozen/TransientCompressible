import os
import time
import platform

import ansys.fluent.core as pyfluent
from ansys.fluent.core import examples
from ansys.fluent.core.solver import (
    BoundaryConditions,
    CellRegisters,
    Contour,
    Controls,
    General,
    Graphics,
    Initialization,
    Mesh,
    PressureInlet,
    PressureOutlet,
    ReportDefinitions,
    ReportFiles,
    ReportPlots,
    RunCalculation,
    Setup,
)
#from ansys.fluent.visualization import GraphicsWindow, Monitor

nozzle_spaceclaim_file, nozzle_intermediary_file = [
    r'transient_compressible\nozzle.dsco',
    r'transient_compressible\nozzle.dsco.pmdb'
]

###############################################################################
# Launch Fluent as a service in meshing mode with double precision running on
# four processors and print Fluent version.

meshing_session = pyfluent.launch_fluent(
    precision="double",
    processor_count=2,
    mode="meshing",
)
print('Fluent Launched')
#time.sleep(125)
print(meshing_session.get_fluent_version())

###############################################################################
# Initialize workflow
# ~~~~~~~~~~~~~~~~~~~
# Initialize the watertight geometry meshing workflow.

meshing_session.workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")

###############################################################################
# Watertight geometry meshing workflow
# ------------------------------------
# The fault-tolerant meshing workflow guides you through the several tasks that
# follow.
#
# Import CAD and set length units
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Import the CAD geometry and set the length units to inches.
geo_import = meshing_session.workflow.TaskObject["Import Geometry"]
geo_import.Arguments.set_state(
    {
        "FileName": nozzle_intermediary_file,
        "Units": "mm"
    }
)

meshing_session.upload(nozzle_intermediary_file)
geo_import.Execute()

###############################################################################
# Add local sizing
# ~~~~~~~~~~~~~~~~
# Add local sizing controls to the faceted geometry.
local_sizing = meshing_session.workflow.TaskObject["Add Local Sizing"]


print(type(local_sizing))

local_sizing.Execute()

surface_mesh = {
    "CFDSurfaceMeshControls": {
        "MaxSize": 30,  # mm
        "MinSize": 2,  # mm
        "SizeFunctions": "Curvature",
    }
}



surface_mesh_gen = meshing_session.workflow.TaskObject["Generate the Surface Mesh"]
surface_mesh_gen.Arguments.set_state(surface_mesh)
surface_mesh_gen.Execute()

# Describe geometry and define the fluid region.

geometry_describe = {
    "SetupType": "The geometry consists of only fluid regions with no voids",
    "WallToInternal": "No",
    "InvokeShareTopology": "No",
    "Multizone": "No",
}

describe_geo = meshing_session.workflow.TaskObject["Describe Geometry"]
describe_geo.Arguments.set_state(
    geometry_describe
)
describe_geo.Execute()

#Boundary Conditions
boundary_condition = {
    "BoundaryLabelList": ["inlet"],
    "BoundaryLabelTypeList": ["pressure-inlet"],
    "OldBoundaryLabelList": ["inlet"],
    "OldBoundaryLabelTypeList": ["velocity-inlet"],
}
meshing_session.workflow.TaskObject["Update Boundaries"].Arguments.set_state(boundary_condition)
meshing_session.workflow.TaskObject["Update Boundaries"].Execute()



meshing_session.workflow.TaskObject["Update Regions"].Execute()

#Boundary Layers
boundary_layer = {
    "NumberOfLayers": 8,
    "TransitionRatio": 0.35,
}
meshing_session.workflow.TaskObject["Add Boundary Layers"].Arguments.update_dict(boundary_layer)
meshing_session.workflow.TaskObject["Add Boundary Layers"].Execute()

# Generate the volume mesh
meshing_session.workflow.TaskObject["Generate the Volume Mesh"].Arguments.setState(
    {
        "VolumeFill": "poly-hexcore",
        # Poly-hexcore mesh combines polyhedral cells with hexahedral core for accuracy and computational efficiency.
        "VolumeFillControls": {
            "BufferLayers": 1,  # Thin buffer to avoid hex-to-poly abruptness
            "HexMaxCellLength": 20,  # mm
            "HexMinCellLength": 5,  # mm
            "PeelLayers": 0,
        },
        "VolumeMeshPreferences": {
            "Avoid1_8Transition": "yes",
            "MergeBodyLabels": "yes",
            "ShowVolumeMeshPreferences": True,
        },
    }
)
meshing_session.workflow.TaskObject["Generate the Volume Mesh"].Execute()


solver = meshing_session.switch_to_solver()

graphics = Graphics(solver)
mesh = Mesh(solver, new_instance_name="mesh-1")
boundary_conditions = BoundaryConditions(solver)

graphics.picture.x_resolution = 650  # Horizontal resolution for clear visualization
graphics.picture.y_resolution = 450  # Vertical resolution matching typical aspect ratio

all_walls = mesh.surfaces_list.allowed_values()

mesh.surfaces_list = all_walls
mesh.options.edges = True
mesh.display()
graphics.views.restore_view(view_name="isometric")
graphics.picture.save_picture(file_name="transient_compressible_2.png")


#Solver Configuration

solver_general_settings = General(solver)

solver_general_settings.units.set_units(
    quantity="pressure",
    units_name="atm",
)
# density-based solver for compressible flow to capture shock behavior accurately.
solver_general_settings.solver.type = "density-based-implicit"
solver_general_settings.operating_conditions.operating_pressure = 0

setup = Setup(solver)

setup.models.energy.enabled = True
setup.materials.fluid["air"].density = {"option": "ideal-gas"}


# Define boundary conditions for the transient compressible flow simulation.
inlet = PressureInlet(solver, name="inlet")
outlet = PressureOutlet(solver, name="outlet")

inlet.momentum.gauge_total_pressure.value = 91192.5  # Pa
inlet.momentum.supersonic_or_initial_gauge_pressure.value = 74666.3925  # Pa

# Low turbulent intensity of 1.5% for smooth inlet flow, typical for nozzle simulations.
inlet.turbulence.turbulent_intensity = 0.015

outlet.momentum.gauge_pressure.value = 74666.3925  # Pa
outlet.turbulence.backflow_turbulent_intensity = 0.015


controls = Controls(solver)
controls.courant_number = 25

#Report Definitions
report_definitions = ReportDefinitions(solver)


report_definitions.surface.create("mass-flow-rate")
report_definitions.surface["mass-flow-rate"] = {
    "report_type": "surface-massflowrate",
    "surface_names": ["outlet"],
}

report_files = ReportFiles(solver)
report_files.create(name="mass_flow_rate_out_rfile")
report_files["mass_flow_rate_out_rfile"] = {
    "report_defs": ["mass-flow-rate"],
    "print": True,
    "file_name": "nozzle_ss.out",
}

report_plots = ReportPlots(solver)

report_plots.create("mass_flow_rate_out_rplot")
report_plots["mass_flow_rate_out_rplot"] = {
    "report_defs": ["mass-flow-rate"],
    "print": True,
}

#Steady State Initialization
solver.settings.file.write_case(file_name="nozzle_steady.cas.h5")

initialize = Initialization(solver)
initialize.hybrid_initialize()

cell_register = CellRegisters(solver)

# Refinement register: Mark cells where density gradient >50% of domain average
cell_register.create(name="density_scaled_gradient_refn")
cell_register["density_scaled_gradient_refn"] = {
    "type": {
        "option": "field-value",
        "field_value": {
            "derivative": {"option": "gradient"},
            "scaling": {"option": "scale-by-global-average"},
            "option": {
                "option": "more-than",
                "more_than": 0.5,  # Threshold: >50% average
            },
            "field": "density",
        },
    }
}
# Coarsening register: Mark cells where density gradient <45% of domain average
cell_register.create(name="density_scaled_gradient_crsn")
cell_register["density_scaled_gradient_crsn"] = {
    "type": {
        "option": "field-value",
        "field_value": {
            "derivative": {"option": "gradient"},
            "scaling": {"option": "scale-by-global-average"},
            "option": {
                "option": "less-than",
                "less_than": 0.45,  # Threshold: <45% average
            },
            "field": "density",
        },
    }
}

# Define adaptation criteria: Refine if gradient is high and refinement level <2; coarsen if low
solver.settings.mesh.adapt.manual_refinement_criteria = (
    "AND(density_scaled_gradient_refn, CellRefineLevel < 2)"
)
solver.settings.mesh.adapt.manual_coarsening_criteria = "density_scaled_gradient_crsn"

solver.tui.mesh.adapt.manage_criteria.add("adaption_criteria_0")

calculation = RunCalculation(solver)
calculation.iterate(iter_count=400)


#Post-Processing
# Create pressure contour
pressure_contour = Contour(solver, new_instance_name="pressure_contour")

pressure_contour.surfaces_list = ["symmetry"]
pressure_contour.display()

graphics.views.restore_view(view_name="front")
graphics.picture.save_picture(file_name="transient_compressible_3.png")

# Create velocity contour
velocity_contour = Contour(solver, new_instance_name="velocity_contour")

velocity_contour.field = "velocity-magnitude"
velocity_contour.surfaces_list = ["symmetry"]
velocity_contour.display()

graphics.views.restore_view(view_name="front")
graphics.picture.save_picture(file_name="transient_compressible_4.jpg")

# save the case and data file
solver.settings.file.write_case_data(file_name="steady_state_nozzle")

#Time dependance
solver_general_settings.solver.time = "unsteady-1st-order"

# Sinusoidal pressure variation at 2200 Hz simulates pulsating flow, with mean pressure of 0.737 atm.
outlet.momentum.gauge_pressure.value = "(0.12*sin(2200[Hz]*t)+0.737)*101325.0[Pa]"

# Configure mesh adaptation: Refine every 25 iterations
solver.tui.mesh.adapt.manage_criteria.edit("adaption_criteria_0", "frequency", "25")

report_files["mass_flow_rate_out_rfile"] = {
    "file_name": "trans-nozzle-rfile.out",
}

report_plots["mass_flow_rate_out_rplot"].x_label = "time-step"

solver.settings.file.write_case(file_name="nozzle_unsteady.cas.h5")

Transient_controls = solver.settings.solution.run_calculation.transient_controls

Transient_controls.time_step_count = 100
Transient_controls.time_step_size = 2.85596e-05  # s: Resolves 2200 Hz oscillations
Transient_controls.max_iter_per_time_step = (
    10  # Ensures convergence within each time step
)

calculation.calculate()


#Close the Fluent session
solver.exit()