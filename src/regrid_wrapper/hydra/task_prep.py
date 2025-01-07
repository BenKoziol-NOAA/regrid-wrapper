import hydra
from hydra.core.config_store import ConfigStore
from omegaconf import DictConfig, OmegaConf

from regrid_wrapper.concrete.core import iter_operations
from regrid_wrapper.context.logging import LOGGER
from regrid_wrapper.model.config import SmokeDustRegridConfig


MAIN_JOB_TEMPLATE = """
#!/usr/bin/env bash
#
#SBATCH --job-name={job_name}
#SBATCH --account=epic
#SBATCH --qos=batch
#_SBATCH --partition=bigmem
#SBATCH --partition=hera
#SBATCH -t 04:00:00
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node=24  # Assuming 24 cores per node, utilize them fully
#SBATCH --ntasks={ntasks}  # Total tasks should be nodes * tasks-per-node

set -e

DIR=/scratch2/NAGAPE/epic/Ben.Koziol/sandbox/regrid-wrapper
CONDAENV=/scratch2/NAGAPE/epic/Ben.Koziol/miniconda/envs/regrid-wrapper

export PATH=${{CONDAENV}}/bin:${{PATH}}
export ESMFMKFILE=${{CONDAENV}}/lib/esmf.mk
export PYTHONPATH=${{DIR}}/src:${{PYTHONPATH}}
export REGRID_WRAPPER_LOG_DIR={log_directory}

cd ${{REGRID_WRAPPER_LOG_DIR}}
mpirun -np {ntasks} python ${{DIR}}/src/regrid_wrapper/hydra/regrid_wrapper_cli.py
"""


def do_task_prep(cfg: SmokeDustRegridConfig) -> None:
    logger = LOGGER.getChild("do_task_prep")
    logger.info(cfg)
    logger.info("creating run directories")
    cfg.root_output_directory.mkdir(exist_ok=False)
    cfg.output_directory.mkdir(exist_ok=False)
    cfg.log_directory.mkdir(exist_ok=False)
    logger.info("creating main job script")
    nodes = cfg.source_definition.rrfs_grids[cfg.target_grid].nodes
    with open(cfg.main_job_path, "w") as f:
        template = MAIN_JOB_TEMPLATE.format(
            job_name=cfg.target_grid.value,
            nodes=nodes,
            ntasks=nodes * 24,
            log_directory=cfg.log_directory,
        )
        logger.info(template)
        f.write(template)


@hydra.main(version_base=None, config_path="conf", config_name="smoke-dust-config")
def do_task_prep_cli(cfg: DictConfig) -> None:
    logger = LOGGER.getChild("regrid_wrapper_app")
    logger.info("start")
    sd_cfg = SmokeDustRegridConfig.model_validate(cfg)
    do_task_prep(sd_cfg)
    logger.info("success")


if __name__ == "__main__":
    do_task_prep_cli()