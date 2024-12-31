from pathlib import Path
import numpy as np

from regrid_wrapper.concrete.rrfs_dust_data import (
    RrfsDustData,
)
from regrid_wrapper.context.comm import COMM
from regrid_wrapper.model.spec import GenerateWeightFileAndRegridFields
from regrid_wrapper.strategy.core import RegridProcessor
import pytest

import xarray as xr
from test.conftest import (
    create_rrfs_grid_file,
    ncdump,
    create_dust_data_file,
)


# @pytest.mark.skip("dev only")
# def test_dev(bin_dir: Path, tmp_path_shared: Path) -> None:
# tdk:rm
#     weight_filename = "weights-veg_map-NA_3km-to-CONUS_25km"
#     spec = GenerateWeightFileAndRegridFields(
#         src_path=bin_dir / "RRFS_NA_3km/veg_map.nc",
#         dst_path=bin_dir / "RRFS_CONUS_25km/ds_out_base.nc",
#         output_weight_filename=tmp_path_shared / weight_filename,
#         output_filename=tmp_path_shared / "veg_map.nc",
#         fields=("emiss_factor",),
#         esmpy_debug=True,
#         name=weight_filename,
#     )
#     op = RrfsSmokeDustVegetationMap(spec=spec)
#     processor = RegridProcessor(operation=op)
#     processor.execute()


@pytest.mark.mpi
def test(tmp_path_shared: Path) -> None:
    src_grid = tmp_path_shared / "src_grid.nc"
    dst_grid = tmp_path_shared / "dst_grid.nc"
    weights = tmp_path_shared / "weights.nc"
    dust_data = tmp_path_shared / "dust.nc"

    if COMM.rank == 0:
        _ = create_dust_data_file(src_grid)
        _ = create_rrfs_grid_file(dst_grid)
    COMM.barrier()

    spec = GenerateWeightFileAndRegridFields(
        src_path=src_grid,
        dst_path=dst_grid,
        output_weight_filename=weights,
        output_filename=dust_data,
        esmpy_debug=True,
        name="dust-data",
    )
    op = RrfsDustData(spec=spec)
    processor = RegridProcessor(operation=op)
    processor.execute()

    assert weights.exists()
    assert dust_data.exists()

    if COMM.rank == 0:
        with xr.open_dataset(src_grid) as ds:
            expected = ds["emiss_factor"]
            # TEST_LOGGER.debug(expected.to_dataframe().describe())
        with xr.open_dataset(veg_map) as ds:
            actual = ds["emiss_factor"]
            # TEST_LOGGER.debug(actual.to_dataframe().describe())
        diff = expected.values - actual.values
        assert np.max(diff) == 0.0
        assert expected.attrs == actual.attrs
        ncdump(veg_map)

        with xr.open_dataset(weights) as ds:
            n_s = ds.sizes["n_s"]
            assert n_s > 0
            # TEST_LOGGER.debug(f"n_s={n_s}")