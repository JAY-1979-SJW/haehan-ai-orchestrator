"use client";
import { useState, useCallback, useRef, useEffect } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";

const AUTH =
  typeof btoa !== "undefined"
    ? `Basic ${btoa("owner:haehan2024!")}`
    : "";

interface Service {
  g: string;
  icon: string;
  name: string;
  desc: string;
  detail: string;   // 채팅창 상세 설명
  tips: string[];   // 이런 분께 추천
  url: string;
  openKey: string;
  doKey: string | null;
  doLabel: string | null;
}

const CATALOG: Service[] = [
  {
    g:"커뮤니케이션", icon:"✉️",  name:"Gmail", url:"https://mail.google.com/",
    desc:"이메일 수신·발송·검색·분석",
    detail:"Gmail은 Google의 이메일 서비스입니다. 스마트 분류(기본·소셜·프로모션)로 중요한 메일을 놓치지 않고, 검색 성능이 뛰어나 수년치 메일도 빠르게 찾을 수 있습니다. 라벨·필터로 자동 정리가 가능하며, 15GB 무료 저장공간을 제공합니다.",
    tips:["비즈니스 이메일을 체계적으로 관리하고 싶은 분","대량 메일 필터링·자동 분류가 필요한 분","메일 기반 고객 응대 자동화를 원하는 분"],
    openKey:"gmail_open", doKey:"gmail_send_email", doLabel:"메일 작성",
  },
  {
    g:"커뮤니케이션", icon:"📅",  name:"캘린더", url:"https://calendar.google.com/",
    desc:"일정 조회·생성·관리",
    detail:"Google 캘린더는 팀 일정 공유와 회의 예약에 특화된 서비스입니다. 다른 사람 캘린더를 구독해 빈 시간을 확인하고 초대를 보낼 수 있으며, Google Meet와 연동되어 화상회의 링크가 자동 생성됩니다. 반복 일정·알림 설정도 유연합니다.",
    tips:["팀원과 일정을 공유하고 조율해야 하는 분","회의 예약·리마인더 자동화가 필요한 분","프로젝트 마일스톤을 시각적으로 관리하고 싶은 분"],
    openKey:"calendar_open", doKey:"calendar_create_event", doLabel:"일정 추가",
  },
  {
    g:"커뮤니케이션", icon:"💬",  name:"Chat", url:"https://chat.google.com/",
    desc:"팀 메시지·공간·메시지 발송",
    detail:"Google Chat은 팀 협업용 메신저로, '스페이스(공간)'를 만들어 프로젝트별로 대화를 분리할 수 있습니다. Google Docs·Sheets·Drive와 긴밀히 연동되어 파일 공유가 간편하고, 봇(Bot)을 통한 업무 자동화도 지원합니다.",
    tips:["Google Workspace를 사용 중인 팀","Slack 대신 Google 생태계 내 메신저가 필요한 분","팀 채널별 파일·대화 관리가 필요한 분"],
    openKey:"chat_open", doKey:"chat_send_message", doLabel:"메시지 발송",
  },
  {
    g:"커뮤니케이션", icon:"🎥",  name:"Meet", url:"https://meet.google.com/",
    desc:"화상회의 참여·회의 생성",
    detail:"Google Meet는 브라우저에서 바로 실행되는 화상회의 서비스입니다. 최대 100명(무료)까지 동시 접속이 가능하며, 화면 공유·실시간 자막·녹화 기능을 제공합니다. 캘린더와 연동하면 회의 링크가 초대장에 자동 포함됩니다.",
    tips:["원격 팀 미팅·화상 면접이 잦은 분","브라우저 설치 없이 바로 쓰고 싶은 분","회의 자동 녹화·자막이 필요한 분"],
    openKey:"meet_open", doKey:"meet_create_meeting", doLabel:"회의 생성",
  },
  {
    g:"커뮤니케이션", icon:"👥",  name:"연락처", url:"https://contacts.google.com/",
    desc:"연락처 조회·생성·수정",
    detail:"Google 연락처는 Gmail·캘린더·Meet와 연동되어 이메일 작성 시 자동완성을 지원합니다. 연락처 그룹을 만들어 대량 메일 발송 목록으로 활용하거나, CSV로 일괄 가져오기/내보내기가 가능합니다.",
    tips:["고객·파트너 연락처를 체계적으로 관리하는 분","메일 수신자 그룹을 자주 사용하는 분","여러 기기 간 연락처 동기화가 필요한 분"],
    openKey:"contacts_open", doKey:"contacts_create_update", doLabel:"연락처 추가",
  },
  {
    g:"업무 도구", icon:"📄",  name:"Docs", url:"https://docs.google.com/",
    desc:"문서 작성·편집·공유",
    detail:"Google Docs는 실시간 공동 편집이 가능한 클라우드 문서 도구입니다. 여러 명이 동시에 편집해도 충돌이 없고, 변경 이력이 자동 저장되어 언제든 이전 버전으로 복원할 수 있습니다. Word 파일 호환 및 PDF 내보내기도 지원합니다.",
    tips:["팀과 문서를 실시간으로 함께 작성해야 하는 분","버전 관리·편집 이력이 중요한 분","언제 어디서나 문서에 접근해야 하는 분"],
    openKey:"docs_open", doKey:"docs_create_edit_document", doLabel:"문서 생성",
  },
  {
    g:"업무 도구", icon:"📊",  name:"Sheets", url:"https://sheets.google.com/",
    desc:"스프레드시트 조회·셀 업데이트",
    detail:"Google Sheets는 실시간 공동 편집이 가능한 스프레드시트입니다. Apps Script로 업무 자동화(데이터 가져오기·이메일 발송 등)를 구현할 수 있고, 피벗 테이블·차트·조건부 서식 등 Excel 수준의 기능을 제공합니다. API 연동으로 데이터 대시보드로 활용 가능합니다.",
    tips:["팀 데이터를 공유하며 실시간으로 업데이트해야 하는 분","Excel 파일을 클라우드로 이전하고 싶은 분","Apps Script로 업무 자동화를 원하는 분"],
    openKey:"sheets_open", doKey:"sheets_update_cells", doLabel:"시트 편집",
  },
  {
    g:"업무 도구", icon:"🎞️", name:"Slides", url:"https://slides.google.com/",
    desc:"프레젠테이션 작성·편집",
    detail:"Google Slides는 실시간 공동 작업이 가능한 프레젠테이션 도구입니다. 다양한 테마·애니메이션을 지원하며, PowerPoint 파일 호환이 가능합니다. 발표 중 Q&A 기능으로 청중의 질문을 실시간 수집할 수 있습니다.",
    tips:["팀 프레젠테이션을 함께 만들어야 하는 분","브라우저에서 바로 발표 자료를 수정하는 분","PPT를 클라우드로 관리하고 싶은 분"],
    openKey:"slides_open", doKey:"slides_create_presentation", doLabel:"슬라이드 생성",
  },
  {
    g:"업무 도구", icon:"📋",  name:"Forms", url:"https://forms.google.com/",
    desc:"설문 생성·배포·응답 수집",
    detail:"Google Forms는 설문조사·퀴즈·신청서를 빠르게 만들 수 있는 도구입니다. 응답 결과가 Google Sheets에 자동으로 집계되어 분석이 편리합니다. 조건 분기 질문, 이미지 첨부, 이메일 알림 등 다양한 기능을 제공합니다.",
    tips:["고객 피드백·설문조사를 자주 진행하는 분","응답 데이터를 자동으로 집계·분석하고 싶은 분","이벤트 신청서·참가 폼이 필요한 분"],
    openKey:"forms_open", doKey:"forms_create_publish", doLabel:"설문 생성",
  },
  {
    g:"업무 도구", icon:"🗒️", name:"Keep", url:"https://keep.google.com/",
    desc:"메모·할일·리마인더 관리",
    detail:"Google Keep은 빠른 메모와 할 일 목록 관리에 최적화된 도구입니다. 위치·시간 기반 리마인더 설정이 가능하고, 사진 속 텍스트를 인식(OCR)하는 기능도 있습니다. Docs에서 Keep 메모를 바로 가져올 수 있어 아이디어를 빠르게 문서화할 수 있습니다.",
    tips:["짧은 메모와 할 일 목록을 빠르게 기록하는 분","위치 기반 리마인더가 필요한 분","아이디어를 즉시 캡처하고 나중에 정리하는 분"],
    openKey:"keep_open", doKey:"keep_create_note", doLabel:"메모 추가",
  },
  {
    g:"업무 도구", icon:"✅",  name:"Tasks", url:"https://tasks.google.com/",
    desc:"작업 목록·완료 체크",
    detail:"Google Tasks는 Gmail·캘린더와 통합된 작업 관리 도구입니다. 이메일에서 바로 할 일로 변환할 수 있고, 하위 작업과 마감일 설정이 가능합니다. 간단한 개인 할 일 관리에 최적화되어 있습니다.",
    tips:["Gmail에서 바로 할 일을 만들고 싶은 분","캘린더와 연동된 간단한 태스크 관리가 필요한 분","복잡한 프로젝트보다 개인 일정 관리에 집중하는 분"],
    openKey:"tasks_open", doKey:"tasks_create_task", doLabel:"작업 추가",
  },
  {
    g:"업무 도구", icon:"⚙️", name:"Apps Script", url:"https://script.google.com/",
    desc:"앱 스크립트 자동화·배포",
    detail:"Google Apps Script는 JavaScript 기반으로 Google 서비스 전체를 자동화할 수 있는 플랫폼입니다. Sheets 데이터를 읽어 Gmail로 자동 발송하거나, Forms 응답을 처리해 Calendar에 일정을 추가하는 등 복잡한 업무 흐름을 코드로 구현할 수 있습니다.",
    tips:["Google 서비스 간 반복 업무를 자동화하고 싶은 분","JavaScript를 알고 있어 스크립트 자동화를 원하는 분","사내 간단한 웹앱을 만들어야 하는 분"],
    openKey:"apps_script_open", doKey:"apps_script_deploy", doLabel:"스크립트 배포",
  },
  {
    g:"저장·미디어", icon:"📁",  name:"Drive", url:"https://drive.google.com/",
    desc:"파일 저장·공유·검색",
    detail:"Google Drive는 15GB 무료 클라우드 스토리지입니다. 팀 드라이브(공유 드라이브)로 조직 파일을 공동 관리할 수 있고, 강력한 검색(이미지 속 텍스트·PDF 내용까지 검색)을 제공합니다. 링크 공유로 권한 설정이 세밀하게 가능합니다.",
    tips:["팀과 파일을 공유하고 공동 관리해야 하는 분","어디서든 파일에 접근해야 하는 분","USB·이메일 첨부 없이 파일을 전달하고 싶은 분"],
    openKey:"drive_open", doKey:"drive_upload_share_file", doLabel:"파일 업로드",
  },
  {
    g:"저장·미디어", icon:"🖼️", name:"Photos", url:"https://photos.google.com/",
    desc:"사진·영상 조회·업로드·공유",
    detail:"Google Photos는 AI 기반 사진 정리 서비스로, 얼굴·장소·사물을 자동 인식해 앨범을 구성합니다. 고화질 압축 저장으로 스마트폰 용량을 절약할 수 있고, 공유 앨범으로 팀·가족과 사진을 쉽게 나눌 수 있습니다.",
    tips:["스마트폰 사진을 자동 백업하고 싶은 분","AI로 사진을 자동 분류·검색하고 싶은 분","팀·행사 사진을 공유 앨범으로 관리하는 분"],
    openKey:"photos_open", doKey:"photos_upload_share", doLabel:"사진 업로드",
  },
  {
    g:"저장·미디어", icon:"▶️", name:"YouTube", url:"https://www.youtube.com/",
    desc:"영상 시청·댓글·구독",
    detail:"YouTube는 세계 최대 동영상 플랫폼입니다. 개인 채널 운영, 광고 수익화(AdSense 연동), 멤버십·슈퍼챗으로 수익 창출이 가능합니다. 이 앱의 YouTube 관리 탭에서 OAuth 인증 후 업로드·자막·채널 관리를 자동화할 수 있습니다.",
    tips:["유튜브 채널을 운영하는 분","영상 콘텐츠로 마케팅을 하는 분","YouTube API로 채널 분석·자동화를 원하는 분"],
    openKey:"youtube_open", doKey:null, doLabel:null,
  },
  {
    g:"저장·미디어", icon:"🎬",  name:"YouTube Studio", url:"https://studio.youtube.com/",
    desc:"영상 업로드·메타데이터·분석",
    detail:"YouTube Studio는 채널 운영자를 위한 관리 대시보드입니다. 영상 업로드·제목·설명·태그 편집, 수익화 설정, 실시간 시청자 분석(조회수·시청 시간·이탈률)을 제공합니다. 댓글 관리 및 커뮤니티 탭 게시도 여기서 합니다.",
    tips:["유튜브 채널 운영자","영상 업로드 후 메타데이터를 최적화하는 분","채널 성장 지표를 분석하고 싶은 분"],
    openKey:"youtube_studio_open", doKey:"youtube_studio_upload_video", doLabel:"영상 업로드",
  },
  {
    g:"마케팅·분석", icon:"📈",  name:"Analytics", url:"https://analytics.google.com/",
    desc:"웹사이트 트래픽·전환 분석",
    detail:"Google Analytics(GA4)는 웹사이트와 앱의 방문자 행동을 분석하는 도구입니다. 방문자 수·체류 시간·전환율을 추적하고, 유입 경로(검색·SNS·직접)별 분석이 가능합니다. 이벤트 기반 추적으로 구매·클릭·폼 제출 등 세부 행동을 측정합니다.",
    tips:["온라인 쇼핑몰·홈페이지 트래픽을 분석하는 분","마케팅 채널별 ROI를 측정하고 싶은 분","전환율 최적화(CRO)를 하는 분"],
    openKey:"analytics_open", doKey:null, doLabel:null,
  },
  {
    g:"마케팅·분석", icon:"📢",  name:"Google Ads", url:"https://ads.google.com/",
    desc:"광고 캠페인 조회·예산 관리",
    detail:"Google Ads는 검색·디스플레이·유튜브·쇼핑 광고를 운영하는 플랫폼입니다. 키워드 입찰로 Google 검색 결과 상단에 광고를 노출하고, 전환 추적으로 실제 구매·문의까지 측정할 수 있습니다. 스마트 캠페인으로 AI 자동 최적화도 가능합니다.",
    tips:["온라인 광고로 매출을 늘리고 싶은 분","키워드 기반 검색 광고를 운영하는 분","스마트스토어 상품을 구글 쇼핑에 노출하고 싶은 분"],
    openKey:"ads_open", doKey:"ads_campaign_budget_change", doLabel:"캠페인 수정",
  },
  {
    g:"마케팅·분석", icon:"🔍",  name:"Search Console", url:"https://search.google.com/search-console/",
    desc:"검색 노출·색인 요청·사이트맵",
    detail:"Google Search Console은 내 사이트가 Google 검색에 어떻게 노출되는지 확인하는 도구입니다. 검색어별 클릭수·노출수·클릭률·평균 순위를 확인하고, 새 페이지를 빠르게 색인 요청하거나 사이트맵을 제출할 수 있습니다. SEO 문제 진단에 필수입니다.",
    tips:["SEO(검색엔진 최적화)를 하는 분","내 사이트의 검색 노출 현황을 파악하고 싶은 분","신규 페이지를 빠르게 구글에 등록하고 싶은 분"],
    openKey:"search_console_open", doKey:"search_console_submit_indexing", doLabel:"색인 요청",
  },
  {
    g:"마케팅·분석", icon:"📉",  name:"Looker Studio", url:"https://lookerstudio.google.com/",
    desc:"데이터 시각화·대시보드 생성",
    detail:"Looker Studio(구 Data Studio)는 무료 데이터 시각화 도구입니다. Google Analytics·Sheets·BigQuery·Ads 등 다양한 소스의 데이터를 연결해 인터랙티브 대시보드를 만들 수 있습니다. 팀과 공유 가능한 실시간 리포트를 빠르게 구성할 수 있습니다.",
    tips:["여러 데이터 소스를 한 화면에서 보고 싶은 분","경영진·팀에게 데이터 리포트를 공유해야 하는 분","Excel 없이 자동 갱신되는 대시보드를 원하는 분"],
    openKey:"looker_studio_open", doKey:null, doLabel:null,
  },
  {
    g:"마케팅·분석", icon:"🛒",  name:"Merchant Center", url:"https://merchants.google.com/",
    desc:"상품 피드·쇼핑 광고 관리",
    detail:"Google Merchant Center는 상품 정보를 Google에 등록해 쇼핑 광고와 무료 쇼핑 탭에 노출하는 플랫폼입니다. 상품 피드(제목·가격·이미지·재고)를 자동 업데이트하고, Google Ads와 연동해 Performance Max 캠페인을 운영할 수 있습니다.",
    tips:["온라인 쇼핑몰 상품을 구글 쇼핑에 노출하고 싶은 분","스마트스토어 상품을 해외 구글 사용자에게 노출하는 분","Google 쇼핑 광고를 시작하려는 분"],
    openKey:"merchant_center_open", doKey:"merchant_center_product_update", doLabel:"상품 업데이트",
  },
  {
    g:"마케팅·분석", icon:"🏪",  name:"Business Profile", url:"https://business.google.com/",
    desc:"비즈니스 정보·게시물 업데이트",
    detail:"Google Business Profile(구 Google 내 비즈니스)은 Google 지도·검색에 내 가게 정보를 관리하는 도구입니다. 영업시간·주소·전화번호·사진을 업데이트하고, 게시물로 이벤트·할인 정보를 노출할 수 있습니다. 리뷰 관리와 Q&A 응답도 여기서 합니다.",
    tips:["오프라인 매장을 운영하는 사업자","구글 지도에 내 사업장을 노출하고 싶은 분","온라인 리뷰를 관리하고 답변해야 하는 분"],
    openKey:"business_profile_open", doKey:"business_profile_post_or_update", doLabel:"게시물 작성",
  },
  {
    g:"클라우드·개발", icon:"☁️", name:"GCP Console", url:"https://console.cloud.google.com/?project=haehan-ai",
    desc:"Cloud Run·GCE·BigQuery 등 16개 서비스",
    detail:"Google Cloud Platform(GCP)은 이 앱의 서버 인프라입니다. Cloud Run으로 컨테이너 배포, Cloud Storage로 파일 저장, BigQuery로 대용량 데이터 분석, Cloud SQL로 DB 관리를 합니다. haehan-ai 프로젝트로 바로 연결됩니다.",
    tips:["서버 배포·인프라 관리가 필요한 개발자","BigQuery로 대용량 데이터를 분석하는 분","이 앱의 Cloud Run 배포 상태를 확인하는 분"],
    openKey:"cloud_console_open", doKey:"cloud_run_deploy_service", doLabel:"서비스 배포",
  },
  {
    g:"클라우드·개발", icon:"🔥",  name:"Firebase", url:"https://console.firebase.google.com/",
    desc:"앱 인증·DB·호스팅·규칙 배포",
    detail:"Firebase는 모바일·웹 앱 개발을 위한 백엔드 플랫폼입니다. Authentication으로 소셜 로그인(Google·카카오 등)을 빠르게 구현하고, Firestore로 실시간 DB를, Hosting으로 정적 웹사이트를 배포할 수 있습니다.",
    tips:["모바일 앱 백엔드가 필요한 개발자","소셜 로그인을 빠르게 구현하고 싶은 분","서버 없이 실시간 데이터 동기화가 필요한 분"],
    openKey:"firebase_console_open", doKey:null, doLabel:null,
  },
  {
    g:"클라우드·개발", icon:"🤖",  name:"AI Studio", url:"https://aistudio.google.com/",
    desc:"Gemini API 테스트·API 키 생성",
    detail:"Google AI Studio는 Gemini 모델을 직접 테스트하고 API 키를 발급받는 플랫폼입니다. 프롬프트를 실험하고 최적의 설정(temperature·max_tokens 등)을 찾은 뒤 코드로 바로 내보낼 수 있습니다. 무료 티어에서도 일정량의 API 호출이 가능합니다.",
    tips:["Gemini API를 활용한 AI 앱을 개발하는 분","Claude 외 Google AI 모델을 비교하고 싶은 분","프롬프트 엔지니어링을 실험하고 싶은 분"],
    openKey:"ai_studio_open", doKey:null, doLabel:null,
  },
  {
    g:"클라우드·개발", icon:"✨",  name:"Gemini", url:"https://gemini.google.com/",
    desc:"Gemini AI 채팅·프롬프트 제출",
    detail:"Gemini는 Google의 최신 AI 어시스턴트입니다. 텍스트·이미지·코드를 이해하고 생성할 수 있으며, Gmail·Docs·Sheets와 통합되어(Gemini for Workspace) 이메일 초안 작성·문서 요약·데이터 분석을 AI로 처리합니다.",
    tips:["Google Workspace에서 AI 어시스턴트를 쓰고 싶은 분","이미지 기반 질문(사진 분석)이 필요한 분","Claude 외 대안 AI 모델을 사용하는 분"],
    openKey:"gemini_open", doKey:null, doLabel:null,
  },
  {
    g:"클라우드·개발", icon:"🔬",  name:"Colab", url:"https://colab.research.google.com/",
    desc:"Python 노트북 실행·ML 실험",
    detail:"Google Colab은 브라우저에서 Python을 실행하는 무료 Jupyter 노트북 환경입니다. GPU/TPU를 무료로 사용할 수 있어 머신러닝·딥러닝 실험에 최적입니다. Google Drive와 연동되어 파일 저장과 공유가 편리합니다.",
    tips:["머신러닝 모델을 실험하는 데이터 과학자","로컬 환경 없이 Python 코드를 실행하고 싶은 분","GPU가 필요한 딥러닝 작업을 무료로 하고 싶은 분"],
    openKey:"colab_open", doKey:null, doLabel:null,
  },
  {
    g:"클라우드·개발", icon:"🎮",  name:"Play Console", url:"https://play.google.com/console/",
    desc:"앱 배포 준비·심사·통계 조회",
    detail:"Google Play Console은 Android 앱을 Google Play 스토어에 배포·관리하는 플랫폼입니다. 앱 등록·심사 제출·버전 관리, 사용자 리뷰 답변, 충돌 보고서 확인, 인앱 결제·구독 설정을 여기서 합니다.",
    tips:["Android 앱을 개발·배포하는 개발자","Play 스토어 앱 리뷰를 관리하는 분","앱 다운로드·수익 지표를 분석하는 분"],
    openKey:"play_console_open", doKey:null, doLabel:null,
  },
  {
    g:"계정·정보", icon:"👤",  name:"내 계정", url:"https://myaccount.google.com/",
    desc:"Google 계정 보안·개인정보 설정",
    detail:"Google 계정 관리 페이지에서 2단계 인증·비밀번호 변경·앱 접근 권한(OAuth 앱 목록)·활동 기록을 관리합니다. 이 앱에서 사용하는 YouTube OAuth 토큰도 여기서 해지하거나 확인할 수 있습니다.",
    tips:["계정 보안을 강화하고 싶은 분","연결된 앱의 OAuth 권한을 확인·해지하는 분","Google 계정의 데이터를 내보내고 싶은 분"],
    openKey:"google_account_open", doKey:null, doLabel:null,
  },
  {
    g:"계정·정보", icon:"🏷️", name:"Tag Manager", url:"https://tagmanager.google.com/",
    desc:"태그 관리·컨테이너 버전 게시",
    detail:"Google Tag Manager(GTM)는 웹사이트에 추적 코드(태그)를 개발자 없이 관리하는 도구입니다. GA4·Google Ads·Facebook Pixel 등을 GTM 하나로 설치·수정하고, 트리거(특정 버튼 클릭, 페이지 스크롤 등) 조건을 설정해 정밀 추적이 가능합니다.",
    tips:["다양한 마케팅 태그를 개발 없이 관리하는 분","GA4 이벤트 추적을 세밀하게 설정하는 분","마케팅 담당자·애널리스트"],
    openKey:"tag_manager_open", doKey:"tag_manager_publish_version", doLabel:"버전 게시",
  },
  {
    g:"계정·정보", icon:"💰",  name:"AdSense", url:"https://adsense.google.com/",
    desc:"광고 수익·광고단위 관리",
    detail:"Google AdSense는 내 웹사이트·블로그·YouTube 채널에 광고를 삽입해 수익을 얻는 서비스입니다. 광고 단위(배너·사각형·인피드)를 만들어 코드를 사이트에 붙이면 Google이 자동으로 적합한 광고를 노출하고 클릭당 수익을 지급합니다.",
    tips:["블로그·콘텐츠 사이트로 광고 수익을 내는 분","YouTube AdSense 수익을 확인하는 분","웹사이트 광고 배치를 최적화하는 분"],
    openKey:"adsense_open", doKey:null, doLabel:null,
  },
];

const GROUPS = [...new Set(CATALOG.map((s) => s.g))];

const GROUP_COLORS: Record<string, { color: string; bg: string; border: string }> = {
  "커뮤니케이션": { color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE" },
  "업무 도구":    { color: "#7C3AED", bg: "#F5F3FF", border: "#DDD6FE" },
  "저장·미디어":  { color: "#C2410C", bg: "#FFF7ED", border: "#FED7AA" },
  "마케팅·분석":  { color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0" },
  "클라우드·개발":{ color: "#0891B2", bg: "#ECFEFF", border: "#A5F3FC" },
  "계정·정보":    { color: "#374151", bg: "#F9FAFB", border: "#E5E7EB" },
};

interface ChatMsg { role: "user" | "ai" | "system"; html: string }

export default function GoogleHubPage() {
  const [query, setQuery]             = useState("");
  const [activeKey, setActiveKey]     = useState<string | null>(null);
  const [msgs, setMsgs]               = useState<ChatMsg[]>([{
    role: "system",
    html: "카드를 클릭하면 서비스 설명이 여기에 표시됩니다.<br>또는 직접 명령어를 입력하세요.",
  }]);
  const [chatInput, setChatInput]     = useState("");
  const [chatRunning, setChatRunning] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const addMsg = useCallback((role: ChatMsg["role"], html: string) => {
    setMsgs((prev) => [...prev, { role, html }]);
  }, []);

  const filtered = CATALOG.filter((s) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.desc.includes(q) || s.g.includes(q);
  });

  const handleCardClick = (s: Service) => {
    const key = s.name;
    setActiveKey(key === activeKey ? null : key);
    const theme = GROUP_COLORS[s.g] ?? GROUP_COLORS["계정·정보"];
    const tipsHtml = s.tips.map((t) => `<li style="margin-top:4px">• ${t}</li>`).join("");
    addMsg("ai",
      `<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">` +
      `<span style="font-size:20px">${s.icon}</span>` +
      `<span style="font-size:13px;font-weight:700;color:#111827">${s.name}</span>` +
      `<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:20px;background:${theme.bg};color:${theme.color};border:1px solid ${theme.border}">${s.g}</span>` +
      `</div>` +
      `<p style="font-size:12px;color:#374151;line-height:1.6;margin-bottom:10px">${s.detail}</p>` +
      `<p style="font-size:11px;font-weight:700;color:#6B7280;margin-bottom:4px">이런 분께 추천</p>` +
      `<ul style="font-size:11px;color:#6B7280;padding:0;list-style:none;margin-bottom:10px">${tipsHtml}</ul>` +
      `<a href="${s.url}" target="_blank" rel="noopener noreferrer" ` +
      `style="display:inline-block;font-size:11px;font-weight:600;padding:5px 12px;border-radius:8px;` +
      `background:${theme.bg};color:${theme.color};border:1px solid ${theme.border};text-decoration:none">` +
      `🔗 ${s.name} 열기</a>`
    );
  };

  const openSite = (e: React.MouseEvent, s: Service) => {
    e.stopPropagation();
    window.open(s.url, "_blank", "noopener,noreferrer");
    addMsg("ai", `<span style="color:#16A34A;font-weight:600">✓ ${s.name}</span> 사이트를 새 탭에서 열었습니다.`);
  };

  const requestAction = async (e: React.MouseEvent, s: Service) => {
    e.stopPropagation();
    if (!s.doKey || !s.doLabel) return;
    addMsg("user", `${s.name} → ${s.doLabel}`);
    try {
      const r = await fetch(`${API_BASE}/api/v1/google/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: AUTH },
        body: JSON.stringify({ host: s.url, action_key: s.doKey }),
      });
      const d = await r.json();
      addMsg("ai", d.ok
        ? `<span style="color:#16A34A;font-weight:600">✅ ${s.doLabel} 완료</span> ${d.message || ""}`
        : `<span style="color:#C2410C;font-weight:600">🔒 승인 필요</span> ${d.reason || d.detail || ""}`
      );
    } catch {
      addMsg("ai", `<span style="color:#DC2626">서버 미연결</span> — 사이트를 직접 이용하세요.`);
    }
  };

  const sendChat = async () => {
    const msg = chatInput.trim();
    if (!msg || chatRunning) return;
    setChatInput("");
    setChatRunning(true);
    addMsg("user", msg);
    try {
      const r = await fetch(`${API_BASE}/api/v1/google/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: AUTH },
        body: JSON.stringify({ message: msg }),
      });
      const d = await r.json();
      addMsg("ai", d.reply || "명령을 처리했습니다.");
    } catch {
      addMsg("ai", `<span style="color:#DC2626">서버 미연결</span> — 직접 사이트를 이용하세요.`);
    } finally {
      setChatRunning(false);
    }
  };

  return (
    <PageShell title="구글 허브" description={`${CATALOG.length}개 Google 서비스`} chatDomain="google">
      {/* 2열 레이아웃: 카드 그리드 | 채팅 패널 */}
      <div className="flex flex-col lg:flex-row gap-4 h-full" style={{ minHeight: "calc(100vh - 120px)" }}>

        {/* ── 좌측: 서비스 카드 그리드 ───────────────────────────────────── */}
        <div className="flex-1 min-w-0 space-y-4 overflow-y-auto pr-1">

          {/* 검색 바 */}
          <div className="bg-white border border-[#E5E7EB] rounded-2xl px-4 py-2.5 flex items-center gap-2 sticky top-0 z-10">
            <span className="text-[#9CA3AF] text-sm shrink-0">🔍</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="서비스 이름·기능 검색..."
              className="flex-1 text-sm outline-none text-[#111827] placeholder:text-[#9CA3AF] bg-transparent"
            />
            {query && (
              <button onClick={() => setQuery("")}
                className="text-xs text-[#9CA3AF] hover:text-[#6B7280] shrink-0">지우기</button>
            )}
            <span className="text-xs text-[#9CA3AF] whitespace-nowrap shrink-0">
              {filtered.length}/{CATALOG.length}
            </span>
          </div>

          {/* 그룹별 카드 */}
          {GROUPS.map((g) => {
            const items = filtered.filter((s) => s.g === g);
            if (!items.length) return null;
            const theme = GROUP_COLORS[g] ?? GROUP_COLORS["계정·정보"];
            return (
              <div key={g} className="space-y-2">
                <p className="text-[10px] font-bold tracking-widest uppercase px-1"
                  style={{ color: theme.color }}>{g}</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2">
                  {items.map((s) => {
                    const isActive = activeKey === s.name;
                    return (
                      <div
                        key={s.name}
                        onClick={() => handleCardClick(s)}
                        className="bg-white border rounded-xl p-3 cursor-pointer transition-all hover:shadow-sm select-none"
                        style={{
                          borderColor: isActive ? theme.color : "#E5E7EB",
                          background:  isActive ? theme.bg : "#FFFFFF",
                        }}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-lg leading-none shrink-0">{s.icon}</span>
                          <span className="text-xs font-semibold text-[#111827] truncate">{s.name}</span>
                        </div>
                        <p className="text-[10px] text-[#6B7280] leading-tight mb-2 line-clamp-2">{s.desc}</p>
                        <div className="flex gap-1 flex-wrap">
                          <button
                            onClick={(e) => openSite(e, s)}
                            className="text-[10px] font-semibold px-2 py-0.5 rounded-md border transition-colors hover:opacity-80"
                            style={{ background: theme.bg, color: theme.color, borderColor: theme.border }}>
                            열기
                          </button>
                          {s.doKey && s.doLabel && (
                            <button
                              onClick={(e) => requestAction(e, s)}
                              className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] hover:bg-[#BBF7D0] transition-colors">
                              {s.doLabel}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* ── 우측: AI 채팅 패널 ─────────────────────────────────────────── */}
        <div className="w-full lg:w-[300px] shrink-0 flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden"
          style={{ height: "480px", position: "sticky", top: 0 }}>

          {/* 헤더 */}
          <div className="px-4 pt-4 pb-3 border-b border-[#F3F4F6] shrink-0">
            <p className="text-sm font-bold text-[#111827]">서비스 안내</p>
            <p className="text-[11px] text-[#9CA3AF] mt-0.5">카드를 클릭하면 상세 설명이 표시됩니다</p>
          </div>

          {/* 메시지 목록 */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
            {msgs.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : m.role === "system" ? "justify-center" : "justify-start"}`}>
                {m.role === "system" ? (
                  <span className="text-[11px] text-[#9CA3AF] italic text-center"
                    dangerouslySetInnerHTML={{ __html: m.html }} />
                ) : (
                  <div
                    className={`max-w-full rounded-xl text-xs leading-relaxed ${
                      m.role === "user"
                        ? "px-3 py-2 bg-[#F97316] text-white rounded-br-sm"
                        : "px-3 py-3 bg-[#F9FAFB] border border-[#F3F4F6] text-[#111827] rounded-bl-sm w-full"
                    }`}
                    dangerouslySetInnerHTML={{ __html: m.html }}
                  />
                )}
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* 입력창 */}
          <div className="px-3 pb-3 pt-2 border-t border-[#F3F4F6] shrink-0 flex gap-2">
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendChat()}
              placeholder="명령어 입력..."
              className="flex-1 px-3 py-1.5 text-xs border border-[#E5E7EB] rounded-xl outline-none focus:border-[#F97316] text-[#111827] placeholder:text-[#9CA3AF]"
            />
            <button
              onClick={sendChat}
              disabled={chatRunning}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors shrink-0 ${
                chatRunning ? "bg-[#E5E7EB] text-[#9CA3AF]" : "bg-[#F97316] text-white hover:bg-[#EA580C]"
              }`}>
              {chatRunning ? "···" : "⚡"}
            </button>
          </div>
        </div>

      </div>
    </PageShell>
  );
}
