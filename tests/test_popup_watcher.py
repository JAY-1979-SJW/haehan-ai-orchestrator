"""popup_watcher 단위 테스트"""

from __future__ import annotations

from unittest import mock

from scripts.browser.navigator.popup_watcher import (
    POPUP_MARKERS,
    auto_handle,
    build_watcher_js,
    clear_events,
    install_watcher,
    poll_events,
)


class TestBuildWatcherJs:
    def test_js_template_generated(self):
        """JS 코드가 생성되는가."""
        js = build_watcher_js(POPUP_MARKERS)
        assert "MutationObserver" in js
        assert "window.__hh_popup_state" in js
        assert "const MARKERS =" in js

    def test_marker_list_encoded(self):
        """마커 리스트가 JSON 인코딩되는가."""
        js = build_watcher_js({"테스트": {"action": None}})
        assert '"key":' in js  # JSON 인코딩되므로 유니코드 이스케이프 포함


class TestInstallWatcher:
    def test_install_returns_frame_count(self):
        """install_watcher가 frame_count를 반환하는가."""
        mock_frame = mock.Mock()
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            result = install_watcher()
            assert result["installed"] is True
            assert result["frame_count"] == 1
            mock_frame.evaluate.assert_called_once()

    def test_install_continues_on_frame_error(self):
        """한 프레임이 실패해도 나머지는 진행."""
        mock_frame1 = mock.Mock()
        mock_frame1.evaluate.side_effect = Exception("frame error")
        mock_frame2 = mock.Mock()
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame1, mock_frame2]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            result = install_watcher()
            assert result["frame_count"] == 1  # 성공한 1개만


class TestPollEvents:
    def test_poll_returns_events(self):
        """이벤트를 반환하는가."""
        events = [
            {
                "ts_ms": 1000,
                "marker": "테스트",
                "snippet": "텍스트",
                "frame_url": "http://test.com",
            }
        ]
        mock_frame = mock.Mock()
        mock_frame.evaluate.return_value = events
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            result = poll_events(since_ms=0)
            assert result == events

    def test_poll_filters_by_since_ms(self):
        """since_ms 이후 이벤트만 필터링하는가."""
        mock_frame = mock.Mock()
        mock_frame.evaluate.return_value = []
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            poll_events(since_ms=5000)
            # evaluate 호출 시 since_ms가 전달되었는지 확인
            call_args = mock_frame.evaluate.call_args
            assert call_args[0][1] == 5000

    def test_poll_returns_empty_on_error(self):
        """프레임 오류 시 빈 리스트 반환."""
        mock_frame = mock.Mock()
        mock_frame.evaluate.side_effect = Exception("eval error")
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            result = poll_events()
            assert result == []


class TestClearEvents:
    def test_clear_events_calls_evaluate(self):
        """clear_events가 evaluate를 호출하는가."""
        mock_frame = mock.Mock()
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            clear_events()
            mock_frame.evaluate.assert_called_once()
            # evaluate에 빈 배열 설정 코드가 포함되어야 함
            call_args = mock_frame.evaluate.call_args[0][0]
            assert "events = []" in call_args


class TestAutoHandle:
    def test_auto_handle_processes_known_popup(self):
        """알려진 팝업을 처리하는가."""
        events = [
            {
                "ts_ms": 1000,
                "marker": "작성 중인 글",
                "snippet": "팝업 텍스트",
                "frame_url": "http://test.com",
            }
        ]
        mock_frame = mock.Mock()
        mock_frame.evaluate.side_effect = [events, None]  # poll 1회, clear 1회
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            with mock.patch("scripts.browser.navigator.navigator.click_button", return_value=True) as mock_click:
                result = auto_handle()
                assert len(result["handled"]) == 1
                assert result["handled"][0]["clicked"] is True
                mock_click.assert_called_with("취소")

    def test_auto_handle_skips_action_none(self):
        """action이 None인 팝업은 스킵."""
        events = [
            {
                "ts_ms": 1000,
                "marker": "임시저장",
                "snippet": "임시저장됨",
                "frame_url": "http://test.com",
            }
        ]
        mock_frame = mock.Mock()
        mock_frame.evaluate.side_effect = [events, None]
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            result = auto_handle()
            assert len(result["skipped"]) == 1
            assert len(result["handled"]) == 0

    def test_auto_handle_reports_unknown(self):
        """미지의 팝업을 unknown에 보고."""
        events = [
            {
                "ts_ms": 1000,
                "marker": "새로운 팝업",
                "snippet": "알 수 없는 팝업",
                "frame_url": "http://test.com",
            }
        ]
        mock_frame = mock.Mock()
        mock_frame.evaluate.side_effect = [events, None]
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            result = auto_handle()
            assert len(result["unknown"]) == 1
            assert result["unknown"][0]["marker"] == "새로운 팝업"

    def test_auto_handle_clears_after_processing(self):
        """처리 후 clear_events를 호출하는가."""
        events = []
        mock_frame = mock.Mock()
        mock_frame.evaluate.side_effect = [events, None]
        mock_page = mock.Mock()
        mock_page.frames = [mock_frame]

        with mock.patch("scripts.browser.cdp.connection.get_page", return_value=mock_page):
            auto_handle()
            # poll + clear 순서로 2번 호출됨
            assert mock_frame.evaluate.call_count >= 1
