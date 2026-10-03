# GitHub 협업 설정

## 이 폴더는 무엇인가

PR 작성과 리뷰를 돕는 저장소 설정을 둔다.

## 입력

변경 목적, 개발 Layer, 관련 계약, 검증 결과.

## 출력

리뷰어가 판단할 수 있는 PR 설명.

## 책임

공통 리뷰 항목을 제공한다.

## 하지 않는 것

연구 설계 정의나 실행 결과 보관.

## 다른 모듈과의 연결

[CONTRIBUTING](../CONTRIBUTING.md)의 작업 규칙을 따른다.

## 현재 상태

PR template, 작업별 Issue Forms, `make check` CI와 weekly Dependabot 설정이 있다.

## 파일 배치 규칙

PR 안내는 pull_request_template.md, 작업 명세는 ISSUE_TEMPLATE/, 자동 검증은 workflows/ci.yml에 둔다. repository UI 설정은 maintainer가 별도로 관리한다.
