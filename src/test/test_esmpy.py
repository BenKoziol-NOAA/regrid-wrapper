from pathlib import Path


from test.conftest import TEST_LOGGER
import esmpy
import numpy as np
import xarray as xr
from mpi4py import MPI


def test() -> None:
    data_dir = Path("/opt/data-root")
    grid = esmpy.Grid(
        filename=str(data_dir / "RRFS_CONUS_3km/grid_in.nc"),
        filetype=esmpy.FileFormat.GRIDSPEC,
    )
    TEST_LOGGER.debug(grid)


def test_regridding_weights() -> None:
    # File paths for input data
    source_grid_spec = "/opt/data-root/RRFS_CONUS_3km/grid_in.nc"
    target_grid_spec = "/opt/data-root/RRFS_CONUS_3km/ds_out_base.nc"
    # emissions_file = "/scratch2/BMC/acomp/Johana.R/RAVE_test_Canada/Hourly_Emissions_3km_202306171500_202306171500.nc"

    # Initialize MPI
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    # Initialize ESMF Manager within the MPI context
    manager = esmpy.Manager(debug=True)
    print(manager.local_pet)
    print(manager.pet_count)

    # Open datasets
    ds_in = xr.open_dataset(source_grid_spec)
    ds_out = xr.open_dataset(target_grid_spec)
    # ds_emissions = xr.open_dataset(emissions_file)

    # Extract coordinate data
    src_latt = ds_in["grid_latt"].values
    src_lont = ds_in["grid_lont"].values
    tgt_latt = ds_out["grid_latt"].values
    tgt_lont = ds_out["grid_lont"].values

    # Adjust longitudes if necessary
    src_lont2 = np.where(src_lont > 0, src_lont, src_lont + 360)

    # Create ESMF Grids
    src_shape = src_latt.shape
    tgt_shape = tgt_latt.shape
    src_grid = esmpy.Grid(
        np.array(src_shape),
        staggerloc=esmpy.StaggerLoc.CENTER,
        coord_sys=esmpy.CoordSys.SPH_DEG,
    )
    tgt_grid = esmpy.Grid(
        np.array(tgt_shape),
        staggerloc=esmpy.StaggerLoc.CENTER,
        coord_sys=esmpy.CoordSys.SPH_DEG,
    )

    # Get local bounds for setting coordinates
    src_x_lb, src_x_ub = (
        src_grid.lower_bounds[esmpy.StaggerLoc.CENTER][1],
        src_grid.upper_bounds[esmpy.StaggerLoc.CENTER][1],
    )
    src_y_lb, src_y_ub = (
        src_grid.lower_bounds[esmpy.StaggerLoc.CENTER][0],
        src_grid.upper_bounds[esmpy.StaggerLoc.CENTER][0],
    )
    tgt_x_lb, tgt_x_ub = (
        tgt_grid.lower_bounds[esmpy.StaggerLoc.CENTER][1],
        tgt_grid.upper_bounds[esmpy.StaggerLoc.CENTER][1],
    )
    tgt_y_lb, tgt_y_ub = (
        tgt_grid.lower_bounds[esmpy.StaggerLoc.CENTER][0],
        tgt_grid.upper_bounds[esmpy.StaggerLoc.CENTER][0],
    )

    # Set coordinates within the local extents of each grid
    src_cen_lon = src_grid.get_coords(0)
    src_cen_lat = src_grid.get_coords(1)
    src_cen_lon[...] = src_lont2[src_y_lb:src_y_ub, src_x_lb:src_x_ub]
    src_cen_lat[...] = src_latt[src_y_lb:src_y_ub, src_x_lb:src_x_ub]

    tgt_cen_lon = tgt_grid.get_coords(0)
    tgt_cen_lat = tgt_grid.get_coords(1)
    tgt_cen_lon[...] = tgt_lont[tgt_y_lb:tgt_y_ub, tgt_x_lb:tgt_x_ub]
    tgt_cen_lat[...] = tgt_latt[tgt_y_lb:tgt_y_ub, tgt_x_lb:tgt_x_ub]

    # Close datasets to free resources
    # ds_in.close()
    ds_out.close()

    # Prepare fields on the grids
    area = ds_in["area"]
    srcfield = esmpy.Field(src_grid, name="test")
    tgtfield = esmpy.Field(tgt_grid, name="test")
    ds_in.close()

    srcfield.data[...] = area[:, :][src_y_lb:src_y_ub, src_x_lb:src_x_ub]
    print("STARTING BIG PART")

    # Parallel computation begins
    if comm.rank == 0:
        print("Starting parallel computation...")

    # Set up the regridder
    regrid_method = esmpy.RegridMethod.NEAREST_DTOS
    # filename = "CONUS_test_MAY15_NEAREST_DTOS.nc"
    filename = "/opt/project/test_is_this_the_script_CONUS_NEAREST_DTOS.nc"
    regridder = esmpy.Regrid(
        srcfield,
        tgtfield,
        regrid_method=regrid_method,
        filename=filename,
        unmapped_action=esmpy.UnmappedAction.IGNORE,
        ignore_degenerate=True,
    )

    # Apply regridding if necessary
    # tgtfield = regridder(srcfield, tgtfield)

    # Clean up and finalize
    esmpy.Manager().finalize()