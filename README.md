# 메모 일정함 설치판

쿨메신저 UDB에서 날짜가 들어간 메시지를 일정 후보로 뽑아 Google Calendar(또는 ICS)로 등록하는 Windows 프로그램입니다. Python 설치가 필요 없습니다.

## 배포 파일 (`dist\`)

| 파일 | 용도 |
| --- | --- |
| `MemoCalendar-Setup.exe` | 정식 설치파일. 설치·제거, 시작 메뉴/바탕화면 바로가기, 시작프로그램 등록(선택) |
| `MemoCalendar-Portable.exe` | 휴대용 단일 EXE. 설치 없이 복사해서 실행 |

두 파일 모두 UDB, 설정, Google 인증정보, 사용 기록을 **포함하지 않습니다**. 새 PC에서는 처음 설정하는 깨끗한 상태로 시작합니다.

## 처음 실행

1. 실행하면 기본 브라우저에 화면이 열립니다.
2. 쿨메신저 UDB를 자동으로 찾습니다. (`%LOCALAPPDATA%\CoolMessenger`, `%APPDATA%\CoolMessenger`, 문서·다운로드, 고정 디스크의 `CoolMessenger` 폴더 등. 쿨메신저 메시지 테이블이 있는 파일만 인정하고 가장 최근 수정된 것을 사용)
3. 못 찾으면 안내 화면의 **UDB 설정하기** 또는 우측 상단 **환경 설정**에서 자동 찾기 / 경로 입력 / 파일 선택을 사용합니다.
4. Google 연결: 환경 설정에서 데스크톱 앱 OAuth JSON을 선택하고 계정을 승인합니다. (연결하지 않아도 ICS 내보내기는 가능)

## 색상 테마 (환경 설정 > 색상 테마)

- 산호(기본, 코랄) / 숲(초록) / 하늘(파랑) / 다크(무채색)

선택한 테마는 PC별로 저장됩니다.

## 시작프로그램과 종료

설치 시 "Windows 시작 시 자동 실행"을 고르면 로그인할 때 화면 없이 백그라운드로 실행됩니다. 바로가기를 누르면 실행 중인 프로그램의 화면이 열립니다. 완전히 끄려면 환경 설정 > 프로그램 종료를 누르세요.

## 저장 위치

`%LOCALAPPDATA%\CoolMemoCalendar` — 설정, 등록 이력, Google 인증정보(Windows DPAPI 암호화, 다른 PC로 복사해도 사용 불가), 로그. 제거 시 함께 삭제할지 묻습니다. 쿨메신저 UDB는 읽기 전용으로만 열며 삭제하지 않습니다.

## 다시 빌드하기

```powershell
pip install pyinstaller pillow
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```
