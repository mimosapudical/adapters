"""TEST ONLY agent: substitutes a local stub transport, never used as parity evidence."""
from pathlib import Path
from medcalc_bench_verified.native_agent import MedCalcNativeAgent

class StubNativeAgent(MedCalcNativeAgent):
    @staticmethod
    def name():
        return "medcalc-offline-stub"
    async def setup(self, environment):
        await super().setup(environment)
        import medcalc_bench_verified.native_runtime as runtime
        await environment.upload_file(Path(runtime.__file__), "/opt/native/native_runtime_core.py")
        await environment.upload_file(Path(__file__).with_name("native_stub_runtime.py"), "/opt/native/runtime.py")
