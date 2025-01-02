import abc
from contextlib import contextmanager
from pathlib import Path
from typing import Tuple, Literal, Dict, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator
import esmpy
import netCDF4 as nc

from mpi4py import MPI


@contextmanager
def open_nc(
    path: Path,
    mode: Literal["r", "w", "a"] = "r",
    clobber: bool = False,
    parallel: bool = True,
) -> nc.Dataset:
    ds = nc.Dataset(
        path,
        mode=mode,
        clobber=clobber,
        parallel=parallel,
        comm=MPI.COMM_WORLD,
        info=MPI.Info(),
    )
    try:
        yield ds
    finally:
        ds.close()


def copy_nc_attrs(src: nc.Dataset | nc.Variable, dst: nc.Dataset | nc.Variable) -> None:
    for attr in src.ncattrs():
        if attr.startswith("_"):
            continue
        setattr(dst, attr, getattr(src, attr))


def resize_nc(
    src_path: Path,
    dst_path: Path,
    new_sizes: Dict[str, int],
    copy_values_for: Sequence[str] | None = None,
) -> None:
    with open_nc(src_path, mode="r") as src:
        with open_nc(dst_path, mode="w") as dst:
            copy_nc_attrs(src, dst)
            for dim in src.dimensions:
                dst.createDimension(dim, size=new_sizes[dim])
            for varname, var in src.variables.items():
                fill_value = (
                    getattr(var, "_FillValue") if hasattr(var, "_FillValue") else None
                )
                new_var = dst.createVariable(
                    varname, var.dtype, var.dimensions, fill_value=fill_value
                )
                copy_nc_attrs(var, new_var)
                if copy_values_for and varname in copy_values_for:
                    new_var[:] = var[:]


class Dimension(BaseModel):
    name: str
    size: int
    lower: int
    upper: int
    staggerloc: int
    coordinate_type: Literal["y", "x", "time"]


class DimensionCollection(BaseModel):
    value: Tuple[Dimension, ...]

    def get(self, name: str) -> Dimension:
        for ii in self.value:
            if ii.name == name:
                return ii
        raise ValueError


def load_variable_data(
    var: nc.Variable, target_dims: DimensionCollection
) -> np.ndarray:
    slices = [
        slice(target_dims.get(ii).lower, target_dims.get(ii).upper)
        for ii in var.dimensions
    ]
    raw_data = var[*slices]
    dim_map = {dim: ii for ii, dim in enumerate(var.dimensions)}
    axes = [dim_map[ii.name] for ii in target_dims.value]
    transposed_data = raw_data.transpose(axes)
    return transposed_data


def set_variable_data(
    var: nc.Variable, target_dims: DimensionCollection, target_data: np.ndarray
) -> np.ndarray:
    dim_map = {dim.name: ii for ii, dim in enumerate(target_dims.value)}
    axes = [dim_map[ii] for ii in var.dimensions]
    transposed_data = target_data.transpose(axes)
    slices = [
        slice(target_dims.get(ii).lower, target_dims.get(ii).upper)
        for ii in var.dimensions
    ]
    var[*slices] = transposed_data
    return transposed_data


class AbstractWrapper(abc.ABC, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    dims: DimensionCollection


class GridSpec(BaseModel):
    x_center: str
    y_center: str
    x_dim: str
    y_dim: str
    x_corner: str | None = None
    y_corner: str | None = None
    x_index: int = 0
    y_index: int = 1

    @property
    def has_corners(self) -> bool:
        return self.x_corner is not None

    def get_x_corner(self) -> str:
        if self.x_corner is None:
            raise ValueError
        return self.x_corner

    def get_y_corner(self) -> str:
        if self.y_corner is None:
            raise ValueError
        return self.y_corner

    def get_x_data(self, grid: esmpy.Grid, staggerloc: esmpy.StaggerLoc) -> np.ndarray:
        return grid.get_coords(self.x_index, staggerloc=staggerloc)

    def get_y_data(self, grid: esmpy.Grid, staggerloc: esmpy.StaggerLoc) -> np.ndarray:
        return grid.get_coords(self.y_index, staggerloc=staggerloc)

    def create_grid_dims(
        self, grid: esmpy.Grid, staggerloc: esmpy.StaggerLoc
    ) -> DimensionCollection:
        grid_shape = grid.max_index
        dims = DimensionCollection(
            value=[
                Dimension(
                    name=self.x_dim,
                    size=grid_shape[self.x_index],
                    lower=grid.lower_bounds[staggerloc][self.x_index],
                    upper=grid.upper_bounds[staggerloc][self.x_index],
                    staggerloc=staggerloc,
                    coordinate_type="x",
                ),
                Dimension(
                    name=self.y_dim,
                    size=grid_shape[self.y_index],
                    lower=grid.lower_bounds[staggerloc][self.y_index],
                    upper=grid.upper_bounds[staggerloc][self.y_index],
                    staggerloc=staggerloc,
                    coordinate_type="y",
                ),
            ]
        )
        return dims


class GridWrapper(AbstractWrapper):
    value: esmpy.Grid
    spec: GridSpec

    def fill_nc_variables(self, path: Path):
        # tdk: needs to work with corners
        with open_nc(path, "a") as ds:
            staggerloc = esmpy.StaggerLoc.CENTER
            x_center_data = self.spec.get_x_data(self.value, staggerloc)
            set_variable_data(
                ds.variables[self.spec.x_center], self.dims, x_center_data
            )
            y_center_data = self.spec.get_y_data(self.value, staggerloc)
            set_variable_data(
                ds.variables[self.spec.y_center], self.dims, y_center_data
            )


class NcToGrid(BaseModel):
    path: Path
    spec: GridSpec

    def create_grid_wrapper(self) -> GridWrapper:
        with open_nc(self.path, "r") as ds:
            grid_shape = np.array(
                [
                    ds.dimensions[self.spec.x_dim].size,
                    ds.dimensions[self.spec.y_dim].size,
                ]
            )
            staggerloc = esmpy.StaggerLoc.CENTER
            grid = esmpy.Grid(
                grid_shape,
                staggerloc=staggerloc,
                coord_sys=esmpy.CoordSys.SPH_DEG,
            )
            dims = self.spec.create_grid_dims(grid, staggerloc)
            grid_x_center_coords = self.spec.get_x_data(grid, staggerloc)
            grid_x_center_coords[:] = load_variable_data(
                ds.variables[self.spec.x_center], dims
            )
            grid_y_center_coords = self.spec.get_y_data(grid, staggerloc)
            grid_y_center_coords[:] = load_variable_data(
                ds.variables[self.spec.y_center], dims
            )
            # tdk: needs to work with corners

            gwrap = GridWrapper(value=grid, dims=dims, spec=self.spec)
            return gwrap


class FieldWrapper(AbstractWrapper):
    value: esmpy.Field
    gwrap: GridWrapper

    def fill_nc_variable(self, path: Path):
        with open_nc(path, "a") as ds:
            var = ds.variables[self.value.name]
            set_variable_data(var, self.dims, self.value.data)


class NcToField(BaseModel):
    path: Path
    name: str
    gwrap: GridWrapper
    dim_time: str | None = None
    staggerloc: int = esmpy.StaggerLoc.CENTER

    def create_field_wrapper(self) -> FieldWrapper:
        with open_nc(self.path, "r") as ds:
            if self.dim_time is None:
                ndbounds = None
                target_dims = self.gwrap.dims
            else:
                ndbounds = (ds.dimensions[self.dim_time].size,)
                time_dim = Dimension(
                    name=self.dim_time,
                    size=ndbounds[0],
                    lower=0,
                    upper=ndbounds[0],
                    staggerloc=self.staggerloc,
                    coordinate_type="time",
                )
                target_dims = DimensionCollection(
                    value=list(self.gwrap.dims.value) + [time_dim]
                )
            field = esmpy.Field(
                self.gwrap.value,
                name=self.name,
                ndbounds=ndbounds,
                staggerloc=self.staggerloc,
            )
            field.data[:] = load_variable_data(ds.variables[self.name], target_dims)
            fwrap = FieldWrapper(value=field, dims=target_dims, gwrap=self.gwrap)
            return fwrap


class FieldWrapperCollection(BaseModel):
    value: Tuple[FieldWrapper, ...]

    def fill_nc_variables(self, path: Path) -> None:
        for fwrap in self.value:
            fwrap.fill_nc_variable(path)

    @field_validator("value", mode="before")
    @classmethod
    def _validate_value_(
        cls, value: Tuple[FieldWrapper, ...]
    ) -> Tuple[FieldWrapper, ...]:
        if len(set([id(ii.value.grid) for ii in value])) != 1:
            raise ValueError("all fields must share the same grid")
        return value
