import abc
import os
from pathlib import Path
from typing import List

import esmpy
from pydantic import BaseModel, model_validator

from regrid_wrapper.context.common import PathType
from regrid_wrapper.context.logging import LOGGER


class AbstractRegridSpec(BaseModel, abc.ABC):
    name: str
    nproc: int = 1
    esmpy_debug: bool = False


class GenerateWeightFileSpec(AbstractRegridSpec):
    src_path: PathType
    dst_path: PathType
    output_weight_filename: PathType

    def is_complete(self) -> bool:
        return self.output_weight_filename.exists()

    @model_validator(mode="after")
    def _validate_model_(self) -> "GenerateWeightFileSpec":
        errors = []
        errors += self._validate_input_file_path_(self.src_path)
        errors += self._validate_input_file_path_(self.dst_path)
        errors += self._validate_output_file_(self.output_weight_filename)
        if errors:
            LOGGER.error(errors)
            raise IOError(errors)
        return self

    @staticmethod
    def _validate_input_file_path_(path: Path) -> List[str]:
        errors = []
        if not path.exists():
            errors.append(f"path does not exist: {path}")
        if not path.is_file():
            errors.append(f"path is not a file: {path}")
        if not os.access(path, os.R_OK):
            errors.append(f"path is not readable: {path}")
        return errors

    @staticmethod
    def _validate_output_file_(path: Path) -> List[str]:
        errors = []
        parent = path.parent
        if not parent.exists():
            errors.append(f"parent directory does not exist: {path.parent}")
        if not os.access(parent, os.W_OK):
            errors.append(f"parent directory is not writable: {path.parent}")
        return errors


class AbstractRegridOperation(abc.ABC):

    def __init__(self, spec: AbstractRegridSpec) -> None:
        self._spec = spec
        self._logger = LOGGER.getChild("operation").getChild(spec.name)
        self._esmf_manager: None | esmpy.Manager = None

    def initialize(self) -> None:
        self._logger.info(f"initializing regrid operation: {self._spec.name}")
        self._esmf_manager = esmpy.Manager(debug=self._spec.esmpy_debug)

    @abc.abstractmethod
    def run(self) -> None: ...

    def finalize(self) -> None:
        self._logger.info(f"finalizing regrid operation: {self._spec.name}")