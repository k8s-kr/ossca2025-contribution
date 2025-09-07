Hugo-based Kubernetes contributions dashboard

이 저장소는 kubernetes 리포지토리의 기여 통계를 수집해 Hugo로 정적 대시보드를 생성하는 예제입니다.

요약 (이 저장소에서 사용하는 기본 워크플로)
- 데이터 수집: `ossca-k8s-contributions.sh` (쉘 스크립트)를 사용해 기간별 기여 요약을 출력합니다.
- (선택) 초기 Python 스크립트 `scripts/fetch_contribs.py`는 보관되어 있으며 향후 개선 지점(더 정교한 JSON 출력 및 중복 제거 등)으로 남겨두었습니다.
- Hugo로 사이트를 빌드하면 `site/public/`에 정적 파일이 생성됩니다.

필수 도구
- bash, curl, jq, gh (GitHub CLI)
- GITHUB_TOKEN 환경변수 (Personal Access Token) — API 접근 및 일부 curl 호출에 사용
- Hugo (사이트 빌드용, 선택적) — https://gohugo.io/getting-started/installation/

빠른 시작

1) (선택) 로컬 의존성 설치 (Python 관련 도구는 `fetch_contribs.py`용이며 현재 선택 사항)

```bash
python3 -m pip install -r requirements.txt
```

2) 기간별 기여 요약 생성 (쉘 스크립트 사용)

```bash
export GITHUB_TOKEN="<your_token>"
./ossca-k8s-contributions.sh 2025-08-31 2025-09-06 > data/2025-08-31..2025-09-06.txt
```

위 명령은 지정한 기간의 요약(표 및 사용자별 항목 목록)을 표준출력으로 출력하므로 파일로 리다이렉트해 `data/` 아래에 저장할 수 있습니다.

3) (옵션) generator로 Hugo 컨텐츠 생성

이 저장소는 `scripts/generate_hugo_from_overall.py` 를 사용해 `data/*.txt` 파일로부터 `site/content/periods/.../_index.md` 또는 `site/content/overall/_index.md` 를 생성합니다. 예:

```bash
python3 scripts/generate_hugo_from_overall.py data/2025-08-31..2025-09-06.txt
```

4) Hugo로 사이트 빌드

```bash
cd site
hugo --minify
```

빌드 결과는 `site/public/` 에 생성됩니다. 로컬에서 확인하려면 간단한 정적 서버를 띄우세요:

```bash
cd site/public
python3 -m http.server 8000
# 브라우저에서 http://localhost:8000 로 접속
```

자동화 예제 (cron)

```cron
0 2 * * * cd /home/ian/git/ianychoi/ossca2025 && /usr/bin/env bash -lc 'export GITHUB_TOKEN="<token>"; ./ossca-k8s-contributions.sh 2025-08-31 2025-09-06 > data/$(date +"%Y-%m-%d")..$(date +"%Y-%m-%d").txt; cd site; hugo --minify'
```

참고: `fetch_contribs.py`에 대한 메모

- 이 저장소에는 `scripts/fetch_contribs.py` 가 남아 있습니다. 현재 기본 워크플로는 `ossca-k8s-contributions.sh` 를 사용하지만, `fetch_contribs.py`는 앞으로의 개선 지점으로 남겨둡니다. 개선 아이디어:
  - JSON 출력의 중복 제거 및 정규화
  - GraphQL 집계 정확도 향상
  - 더 많은 메타데이터(타입 구분, 타임스탬프 표준화) 포함

기타 노트
- GitHub CLI(`gh`)가 설치되어 있고 인증되어 있어야 `ossca-k8s-contributions.sh` 내의 `gh` 호출이 동작합니다. `gh auth login` 으로 먼저 인증하세요.
- 레이트 리미트: Personal Access Token을 사용해 호출 한도를 늘리세요.

```

GitHub Pages에 배포하기

1. 이 저장소에 위에서 추가한 GitHub Actions 워크플로(`.github/workflows/deploy.yml`)가 푸시될 때마다 자동으로 `site` 디렉터리의 Hugo 사이트를 빌드하고 `gh-pages` 브랜치로 배포합니다.
2. 리포지토리의 Settings > Pages로 이동해 배포 소스(Deploy from)를 `gh-pages` 브랜치로 선택하고 `/ (root)`를 지정하세요. 워크플로가 `gh-pages` 브랜치에 파일을 푸시하면 사이트가 활성화됩니다.
3. 도메인, HTTPS 설정 등은 Pages 설정 페이지에서 필요에 따라 구성하세요.

참고: Actions가 `GITHUB_TOKEN`을 사용해 `gh-pages` 브랜치로 푸시하므로 별도 퍼스널 액세스 토큰이 필요하지 않습니다. 단, 조직 정책이나 커스텀 배포(예: 외부 호스팅)에는 추가 설정이 필요할 수 있습니다.

