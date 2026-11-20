"""파이프라인 공통 설정과 도우미 함수."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
WORK = ROOT / "data" / "work"
WEB = ROOT / "web"
KIT = ROOT / "kit"
DOCS = ROOT / "docs"
WORK.mkdir(parents=True, exist_ok=True)

# 원본 필드명 -> 우리가 쓰는 이름
FIELD_MAP = {
    "travllgfrstnm": "name",
    "matrlnmplc": "address",
    "mainfoftrnm": "species",
    "mainfrtpnm": "forest_type",
    "zonearea": "area",
    "histrexmnncont": "history",
    "clturexmnncont": "culture",
}

SIDO_SHORT = {
    "서울특별시": "서울", "서울시": "서울", "서울": "서울",
    "부산광역시": "부산", "부산시": "부산", "부산": "부산",
    "대구광역시": "대구", "대구시": "대구", "대구": "대구",
    "인천광역시": "인천", "인천시": "인천", "인천": "인천",
    "광주광역시": "광주", "광주시": "광주", "광주": "광주",
    "대전광역시": "대전", "대전시": "대전", "대전": "대전",
    "울산광역시": "울산", "울산시": "울산", "울산": "울산",
    "세종특별자치시": "세종", "세종시": "세종", "세종": "세종",
    "경기도": "경기", "경기": "경기",
    "강원도": "강원", "강원특별자치도": "강원", "강원": "강원",
    "충청북도": "충북", "충북": "충북",
    "충청남도": "충남", "충남": "충남",
    "전라북도": "전북", "전북특별자치도": "전북", "전북": "전북",
    "전라남도": "전남", "전남": "전남",
    "경상북도": "경북", "경북": "경북",
    "경상남도": "경남", "경남": "경남",
    "제주특별자치도": "제주", "제주도": "제주", "제주": "제주",
}
SIDO_LONG = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}


def s(v):
    """None, 공백 한 칸 같은 값을 빈 문자열로 정리."""
    return (v or "").strip()


def cp949_bytes(text):
    return len(text.encode("cp949", errors="replace"))


def norm_for_match(text):
    """원문 대조용 정규화: 공백과 문장부호 차이를 무시한다."""
    text = re.sub(r"\s+", "", text or "")
    return re.sub(r"[.,·ㆍ'\"‘’“”()（）\[\]!?~\-:;]", "", text)


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_env():
    """.env 파일을 읽어 환경변수로 넣는다 (python-dotenv 없이)."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env(name, default=None):
    load_env()
    return os.environ.get(name, default)


def need_env(name):
    v = env(name)
    if not v:
        raise SystemExit(f"환경변수 {name} 가 없습니다. 프로젝트 폴더의 .env 파일을 확인하세요 (.env.example 참고).")
    return v
