# 저장소 전용 메모리 인증 구성 증거

2026-09-21. 인증 전 구성·모의검사 기록과, 이후 실제 hyun2277 계정 확인·원격 fetch 증거를 구분해 보존한다.

- 이 작업 전용 Git credential-cache 및 helper 설정이다. 토큰 자체를 저장한 파일은 없다.
- 모의 보안 검사 11개가 통과했다. 이 검사는 실제 GitHub 인증·push 성공을 의미하지 않는다.
- helper의 store 동작은 무시한다. 실제 login 시 28800초를 지정해 한 번만 보관하며, Git 사용으로 자동 연장하지 않는다.
- 정상 실행 파일은 작업 루트의 logs/git-records-20260921/physx_auth_session.py이다. 여기에 있는 복사본은 검토용이며 현재 컴퓨터의 절대 경로에 의존한다.
- 일반 사용은 login/status/stop뿐이다. helper get 또는 git credential fill을 터미널·일반 로그에서 직접 실행하면 비밀이 노출될 수 있으므로 사용하지 않는다. FIFO 검사는 동일 Linux 계정의 다른 프로그램과 격리를 보장하지 않는다.
- Git helper와 cache 사이 비밀 전달 스트림은 로그 수집에서 제외한다. 상태·성공/실패·오류 코드는 비밀 없는 구조화 기록만 남긴다.
- 종료는 작업 도구의 stop으로 전용 캐시만 비우며, GitHub PAT 폐기는 별도이다.

- authenticated-prepush-confirmation.json과 authenticated-fetch.*는 실제 계정 확인과 원격 조회 성공의 증거다. 실제 push 및 원격 SHA 일치 확인은 별도 결과 기록을 따른다.
