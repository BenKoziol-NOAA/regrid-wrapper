from regrid_wrapper.model.regrid_operation import (
    AbstractRegridOperation,
    GenerateWeightFileSpec,
)
from regrid_wrapper.strategy.core import RegridProcessor
from pytest_mock import MockerFixture


class MockRegridOperation(AbstractRegridOperation):

    def run(self) -> None: ...


class TestRegridProcessor:

    def test_happy_path_mock(
        self, fake_spec: GenerateWeightFileSpec, mocker: MockerFixture
    ) -> None:
        print(type(mocker))
        spies = [
            mocker.spy(MockRegridOperation, ii)
            for ii in ["initialize", "run", "finalize"]
        ]
        op = MockRegridOperation(fake_spec)
        processor = RegridProcessor(op)
        processor.execute()
        for spy in spies:
            spy.assert_called_once()
