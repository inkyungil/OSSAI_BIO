"""워크플로 단계를 순서와 게이트째로 실행한다.

명령 11개를 외우지 않으려고 만든 것이 아니다. **순서 자체가 규율**이기 때문에 만들었다.

sealed_test를 마지막에 한 번만 보는 것, 운영점을 validation에서만 고르는 것, 최종 실행
전에 예측을 등록하는 것은 지금까지 사람이 순서를 지켜서 성립했다. 사람이 지키는 규율은
급할 때 깨지고, 깨져도 흔적이 남지 않는다. 여기서는 그것을 **코드가 거부**한다.

    - 예측을 등록하지 않으면 sealed_test가 시작되지 않는다
    - 운영점을 고르지 않으면 seal 단계에 들어갈 수 없다
    - 이미 본 sealed_test는 --force 없이 다시 돌지 않는다
    - 실제 호출은 --live를 직접 적어야만 일어난다

편의는 곁가지고, 규율을 기계가 강제하는 것이 목적이다.

    python run.py check                환경 확인
    python run.py prepare              데이터 준비 ①~⑥
    python run.py develop --live       development + validation + 운영점 선택
    python run.py ablate --live        근거 절제 (XAI)
    python run.py seal --live          예측 등록 → sealed_test → 대조 → 운영점 적용
    python run.py freeze               회귀 fixture 고정
    python run.py dashboard            검토 화면 생성
    python run.py test                 replay 회귀 테스트 (API 호출 없음)

무엇이 돌지 먼저 보려면 어느 단계든 --dry-run을 붙인다.

모든 단계를 한 번에 도는 `all`은 일부러 없다. 그런 명령이 있으면 sealed_test가 다른
단계에 섞여 무심코 소비된다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 한국어 콘솔(cp949)에서 인코딩할 수 없는 글자가 섞여도 러너가 죽지 않게 한다.
# 진행 안내 한 글자 때문에 워크플로가 중단되면 그게 더 나쁘다.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPTS = PROJECT_ROOT / "scripts"
CONFIG = "configs/relation-nim.yaml"
ABLATION_CONFIG = "configs/relation-nim-ablation.yaml"
PREDICTION = PROJECT_ROOT / "data/sealed-test-prediction.json"


class GateError(Exception):
    """규율 위반이라 실행을 시작조차 하지 않는 경우."""


@dataclass
class Step:
    script: str
    args: list[str] = field(default_factory=list)
    why: str = ""


@dataclass
class Paths:
    cases: Path
    corpus: Path
    output: Path
    ablation_output: Path

    @property
    def observations(self) -> Path:
        return self.output / "observations.jsonl"

    @property
    def ablation_observations(self) -> Path:
        return self.ablation_output / "observations.jsonl"

    @property
    def operating_point(self) -> Path:
        return self.output / "operating-point" / "operating-point.json"

    def results(self, split: str) -> Path:
        return self.output / split / "results.jsonl"


def load_paths() -> Paths:
    """config에 적힌 경로를 그대로 읽는다. 러너가 경로를 따로 알면 언젠가 어긋난다."""
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - 환경 문제는 즉시 드러나야 한다
        raise GateError(
            "PyYAML이 없습니다. 이 저장소의 .venv로 실행하세요:\n"
            "  .venv\\Scripts\\python.exe relation-workflow\\run.py ..."
        ) from exc

    def read(name: str) -> dict:
        return yaml.safe_load((PROJECT_ROOT / name).read_text(encoding="utf-8"))["paths"]

    main_paths = read(CONFIG)
    return Paths(
        cases=PROJECT_ROOT / main_paths["cases"],
        corpus=PROJECT_ROOT / main_paths["note_corpus"],
        output=PROJECT_ROOT / main_paths["output"],
        ablation_output=PROJECT_ROOT / read(ABLATION_CONFIG)["output"],
    )


def require_live(live: bool, stage: str) -> None:
    if not live:
        raise GateError(
            f"{stage} 단계는 실제 API를 호출합니다. 비용이 드는 실행이므로\n"
            f"--live를 직접 적어야 합니다:\n"
            f"  python run.py {stage} --live"
        )


# ----- 단계별 계획 -------------------------------------------------------------
# 각 함수는 게이트를 먼저 확인하고 실행할 Step 목록을 돌려준다. 게이트가 막으면
# 한 줄도 실행되지 않는다 - 절반만 돈 상태가 제일 해석하기 어렵기 때문이다.


def plan_check(_paths: Paths, _args: argparse.Namespace) -> list[Step]:
    return [Step("check_environment.py", why="의존성과 패키지 import 확인")]


def plan_prepare(paths: Paths, args: argparse.Namespace) -> list[Step]:
    if paths.cases.is_file() and not args.force:
        raise GateError(
            f"이미 준비된 코퍼스가 있습니다: {paths.cases}\n"
            "prepare를 다시 돌리면 노트 코퍼스가 초기화되고 주입 노트 병합도 되돌아갑니다.\n"
            "정말 처음부터 다시 만들려면 --force를 붙이세요."
        )
    return [
        Step("prepare_relation_notes.py", why="① 노트 108건 복원"),
        Step("prepare_relation_candidates.py", why="② 후보 123쌍 - 원본 엣지 67개 재현을 강제한다"),
        Step("make_labeling_template.py", why="③ 라벨링 편집 틀"),
        Step("draft_relation_labels.py", why="④ 문형 규칙으로 초안 채우기"),
        Step("merge_injection_cases.py", why="⑤ 주입 3건 합치기"),
        Step("prepare_relation_cases.py", why="⑥ 평가용 JSONL"),
    ]


def plan_develop(paths: Paths, args: argparse.Namespace) -> list[Step]:
    require_live(args.live, "develop")
    if not paths.cases.is_file():
        raise GateError(f"평가 케이스가 없습니다: {paths.cases}\n  python run.py prepare")

    # 관찰 로그는 split을 가로질러 쌓인다. 이미 있으면 이어서 도는 것이 정상 경로다.
    resume = ["--resume"] if paths.observations.is_file() else []
    if resume:
        print(f"관찰 로그가 있어 --resume으로 이어서 실행합니다: {paths.observations}")

    return [
        Step(
            "run_relation_nim.py",
            ["--live", "--split", "development", *resume],
            "프롬프트를 고칠 수 있는 유일한 split",
        ),
        Step(
            "run_relation_nim.py",
            ["--live", "--split", "validation", "--resume"],
            "임계값만 고른다 - 프롬프트는 여기서 고치지 않는다",
        ),
        Step("select_operating_point.py", why="운영점 선택 (validation 전용)"),
    ]


def plan_ablate(paths: Paths, args: argparse.Namespace) -> list[Step]:
    require_live(args.live, "ablate")
    if not paths.results("validation").is_file():
        raise GateError(
            f"절제할 판정 결과가 없습니다: {paths.results('validation')}\n"
            "  python run.py develop --live"
        )
    resume = ["--resume"] if paths.ablation_observations.is_file() else []
    return [
        Step("run_ablation_nim.py", ["--live", *resume], "근거를 지우면 판정이 바뀌는지 본다"),
        Step("merge_ablation.py", why="판정 정확도와 근거 충실도를 교차표로 묶는다"),
    ]


def plan_seal(paths: Paths, args: argparse.Namespace) -> list[Step]:
    """이 프로젝트에서 되돌릴 수 없는 유일한 단계. 게이트가 가장 촘촘하다."""
    require_live(args.live, "seal")

    if not paths.operating_point.is_file():
        raise GateError(
            f"운영점이 아직 없습니다: {paths.operating_point}\n"
            "운영점은 validation에서 골라야 합니다. sealed_test를 보고 고르면 그 순간\n"
            "sealed_test가 선택셋이 되어 최종 수치가 근거를 잃습니다 (day5 p37-38).\n"
            "  python run.py develop --live"
        )

    sealed_results = paths.results("sealed_test")
    if sealed_results.is_file() and not args.force:
        raise GateError(
            f"sealed_test는 이미 실행됐습니다: {sealed_results}\n"
            "한 번만 보기로 한 split입니다. 결과를 본 뒤 다시 돌리면 그 수치는\n"
            "더 이상 사전등록된 예측의 검증이 아닙니다.\n"
            "정말 다시 돌려야 한다면 --force를 붙이고, 그 사실을 docs에 남기세요."
        )

    steps: list[Step] = []
    if PREDICTION.is_file():
        print(f"사전등록된 예측을 사용합니다: {PREDICTION}")
    else:
        steps.append(
            Step(
                "register_sealed_prediction.py",
                ["register"],
                "실행 **전에** 예측을 고정한다 - 사후 설명과 증거의 무게가 다르다",
            )
        )

    steps += [
        Step("run_relation_nim.py", ["--live", "--split", "sealed_test", "--resume"], "최종 1회"),
        Step("register_sealed_prediction.py", ["check"], "등록한 예측과 실제 결과 대조"),
        Step("apply_operating_point.py", why="운영점 적용 - 재선택이 아니다"),
    ]
    return steps


def plan_freeze(paths: Paths, _args: argparse.Namespace) -> list[Step]:
    if not paths.observations.is_file():
        raise GateError(f"고정할 실행 결과가 없습니다: {paths.observations}")
    return [Step("freeze_relation_responses.py", why="실제 응답을 회귀 fixture로 고정")]


def plan_dashboard(paths: Paths, _args: argparse.Namespace) -> list[Step]:
    splits = ("development", "validation", "sealed_test")
    if not any(paths.results(split).is_file() for split in splits):
        raise GateError("표시할 결과가 없습니다. 먼저 develop 단계를 실행하세요.")
    return [Step("build_dashboard.py", why="외부 요청 0건인 자립 HTML 한 파일")]


PLANS = {
    "check": plan_check,
    "prepare": plan_prepare,
    "develop": plan_develop,
    "ablate": plan_ablate,
    "seal": plan_seal,
    "freeze": plan_freeze,
    "dashboard": plan_dashboard,
}


def run_steps(steps: list[Step], dry_run: bool) -> int:
    for index, step in enumerate(steps, start=1):
        head = f"[{index}/{len(steps)}] {step.script} {' '.join(step.args)}".rstrip()
        # flush 없이는 부모의 print가 버퍼에 남아 자식 출력 뒤에 찍힌다. 어느 단계의
        # 출력인지 헷갈리면 진행 표시가 아니라 방해가 된다.
        print(f"\n{head}", flush=True)
        if step.why:
            print(f"        {step.why}", flush=True)
        if dry_run:
            continue
        code = subprocess.run(
            [sys.executable, str(SCRIPTS / step.script), *step.args], cwd=PROJECT_ROOT
        ).returncode
        if code != 0:
            # 뒤 단계는 앞 단계 산출물을 전제한다. 실패한 채로 밀고 가면 원인이 묻힌다.
            print(f"\n{step.script} 실패 (exit {code}) - 여기서 멈춥니다", file=sys.stderr)
            return code
    if dry_run:
        print("\n--dry-run: 아무것도 실행하지 않았습니다")
    return 0


def run_tests(dry_run: bool) -> int:
    argv = [sys.executable, "-m", "pytest", str(PROJECT_ROOT / "tests"), "-q"]
    print("\npytest tests -q", flush=True)
    print("        저장 응답 replay - API를 호출하지 않는다", flush=True)
    if dry_run:
        return 0
    return subprocess.run(argv, cwd=PROJECT_ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="관계 판정 워크플로 러너 (순서와 게이트를 강제한다)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("stage", choices=[*PLANS, "test"])
    parser.add_argument("--live", action="store_true", help="실제 API 호출을 허용한다")
    parser.add_argument("--force", action="store_true", help="prepare/seal의 보호 게이트를 넘는다")
    parser.add_argument("--dry-run", action="store_true", help="실행하지 않고 계획만 보여준다")
    args = parser.parse_args()

    if args.stage == "test":
        return run_tests(args.dry_run)

    try:
        steps = PLANS[args.stage](load_paths(), args)
    except GateError as exc:
        print(f"\n중단: {exc}", file=sys.stderr)
        return 2
    return run_steps(steps, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
