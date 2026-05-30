"""blog_mixin 블로그 쓰기/상호작용 기능 (BlogWriteMixin).

write/edit/delete_post, upload_image, comment, like, neighbor 추가/삭제,
guestbook 작성, scrap. [docs/module_separation_standard.md]
"""
from __future__ import annotations

import re
import time


class BlogWriteMixin:
    def blog_write_post(self, title: str, body: str,
                        category_no: str = "",
                        tags: list[str] | None = None,
                        image_paths: list[str] | None = None,
                        is_public: bool = True) -> dict:
        """포스트 작성."""
        self.go("https://blog.naver.com/posting/write")
        time.sleep(3)

        try:
            self._page.locator('.se-title-input, #subject').first.fill(title)
            time.sleep(0.5)

            self._page.locator('.se-text-paragraph').first.click()
            time.sleep(0.5)
            self._page.keyboard.type(body)
            time.sleep(0.5)

            if category_no:
                try:
                    self._page.locator('.category_select').first.click()
                    time.sleep(0.5)
                    self._page.locator(f'[data-category-no="{category_no}"]').first.click()
                except Exception:
                    pass

            if tags:
                try:
                    self._page.locator('.tag_input').first.fill(", ".join(tags))
                except Exception:
                    pass

            if image_paths:
                for img_path in image_paths:
                    try:
                        self._page.locator('input[type="file"]').first.set_input_files(img_path)
                        time.sleep(1.5)
                    except Exception:
                        pass

            publish_btn = self._page.locator('.publish_btn, .btn_publish').first
            publish_btn.click()
            time.sleep(2)

            # log_no 파싱
            current_url = self._page.url
            m = re.search(r'/(\d{10,})', current_url)
            log_no = m.group(1) if m else ""

            return {"ok": True, "log_no": log_no, "url": current_url, "error": ""}
        except Exception as e:
            return {"ok": False, "log_no": "", "url": "", "error": str(e)}

    def blog_edit_post(self, blog_id: str, log_no: str,
                       title: str = "", body: str = "",
                       tags: list[str] | None = None) -> dict:
        """포스트 수정."""
        url = f"https://blog.naver.com/PostModify.naver?blogId={blog_id}&logNo={log_no}"
        self.go(url)
        time.sleep(3)

        try:
            if title:
                self._page.locator('.se-title-input, #subject').first.clear()
                self._page.locator('.se-title-input, #subject').first.fill(title)
                time.sleep(0.5)

            if body:
                self._page.locator('.se-text-paragraph').first.click()
                time.sleep(0.5)
                self._page.keyboard.press("Control+A")
                self._page.keyboard.type(body)
                time.sleep(0.5)

            if tags:
                try:
                    self._page.locator('.tag_input').first.clear()
                    self._page.locator('.tag_input').first.fill(", ".join(tags))
                except Exception:
                    pass

            self._page.locator('.save_btn, .btn_save').first.click()
            time.sleep(1.5)

            return {"ok": True, "log_no": log_no, "error": ""}
        except Exception as e:
            return {"ok": False, "log_no": log_no, "error": str(e)}

    def blog_delete_post(self, blog_id: str, log_no: str) -> dict:
        """포스트 삭제."""
        url = f"https://blog.naver.com/{blog_id}/{log_no}"
        self.go(url)
        time.sleep(2)

        try:
            self._page.on("dialog", lambda dialog: dialog.accept())
            self._page.locator('.more_btn, [class*="more"]').first.click()
            time.sleep(0.5)
            self._page.locator('.del_btn, [class*="delete"]').first.click()
            time.sleep(1)
            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_upload_image(self, image_path: str) -> dict:
        """이미지 업로드."""
        try:
            self._page.locator('input[type="file"]').first.set_input_files(image_path)
            time.sleep(2)
            img_url = self._page.evaluate("document.querySelector('.se-image-resource')?.src || ''")
            if img_url:
                return {"ok": True, "image_url": img_url, "error": ""}
            return {"ok": False, "image_url": "", "error": "이미지 URL 추출 실패"}
        except Exception as e:
            return {"ok": False, "image_url": "", "error": str(e)}

    def blog_write_comment(self, post_url: str, text: str) -> dict:
        """댓글 작성."""
        self.go(post_url)
        time.sleep(2.5)

        try:
            comment_input = self._page.locator('.u_cbox_input, .reply_input, #comment_text').first
            comment_input.click()
            comment_input.fill(text)
            time.sleep(0.5)

            submit_btn = self._page.locator('.u_cbox_btn_upload, .btn_comment_write').first
            submit_btn.click()
            time.sleep(1.5)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_delete_comment(self, post_url: str, comment_index: int = 0) -> dict:
        """댓글 삭제."""
        self.go(post_url)
        time.sleep(2.5)

        try:
            delete_btns = self._page.locator('.u_cbox_btn_delete, .btn_delete_comment').all()
            if comment_index < len(delete_btns):
                self._page.on("dialog", lambda dialog: dialog.accept())
                delete_btns[comment_index].click()
                time.sleep(1)
                return {"ok": True, "error": ""}
            return {"ok": False, "error": "댓글 인덱스 초과"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_like_post(self, post_url: str) -> dict:
        """공감 클릭."""
        self.go(post_url)
        time.sleep(2)

        try:
            like_btn = self._page.locator('.u_likeit_text, .sympathy_btn, [class*="like"]').first
            like_btn.click()
            time.sleep(1)

            m = re.search(r"공감\s*\(?\s*(\d+)", self._page.inner_text("body"))
            like_count = int(m.group(1)) if m else 0

            return {"ok": True, "is_liked": True, "like_count": like_count, "error": ""}
        except Exception as e:
            return {"ok": False, "is_liked": False, "like_count": 0, "error": str(e)}

    def blog_unlike_post(self, post_url: str) -> dict:
        """공감 취소."""
        return self.blog_like_post(post_url)

    def blog_add_neighbor(self, target_blog_url: str, is_mutual: bool = False) -> dict:
        """이웃 추가."""
        self.go(target_blog_url)
        time.sleep(2)

        try:
            add_btn = self._page.locator('.btn_add_friend, .add_buddy, [class*="add_neighbor"]').first
            add_btn.click()
            time.sleep(1)

            if is_mutual:
                try:
                    mutual_btn = self._page.locator('.btn_mutual, [class*="mutual"]').first
                    mutual_btn.click()
                except Exception:
                    pass

            confirm_btn = self._page.locator('.btn_confirm, .btn_ok').first
            confirm_btn.click()
            time.sleep(1)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_remove_neighbor(self, target_blog_url: str) -> dict:
        """이웃 삭제."""
        self.go(target_blog_url)
        time.sleep(2)

        try:
            self._page.on("dialog", lambda dialog: dialog.accept())
            del_btn = self._page.locator('.btn_del_friend, .del_buddy, [class*="del_neighbor"]').first
            del_btn.click()
            time.sleep(1)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_write_guestbook(self, blog_url: str, message: str) -> dict:
        """방명록 작성."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        url = f"https://blog.naver.com/GuestBook.naver?blogId={blog_id}"
        self.go(url)
        time.sleep(2)

        try:
            input_field = self._page.locator('#memo_text, .guestbook_input').first
            input_field.fill(message)
            time.sleep(0.5)

            submit_btn = self._page.locator('.btn_register, .btn_submit').first
            submit_btn.click()
            time.sleep(1.5)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def blog_scrap_post(self, post_url: str) -> dict:
        """포스트 스크랩."""
        self.go(post_url)
        time.sleep(2)

        try:
            scrap_btn = self._page.locator('.scrap_btn, [class*="scrap"]').first
            scrap_btn.click()
            time.sleep(1)

            return {"ok": True, "error": ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}
