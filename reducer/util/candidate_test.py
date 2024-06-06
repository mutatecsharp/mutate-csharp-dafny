from pathlib import Path

class FuzzdCandidateTest:
    def __init__(self, program_dir: Path):
        self.program_name = "main"
        self.program_dir = program_dir
        self.program_path = program_dir / "fuzz_d_generation" / f"{self.program_name}.dfy"
