import sys; sys.path.insert(0, '.')
from scripts.web_connector import get_page
page = get_page()
print('URL:', page.url)
print('Title:', page.title())
result = page.evaluate("""() => {
    const hasLoginBtn = !!document.querySelector('a[href*="login"], a[href*="nid.naver"]');
    const hasProfile = !!document.querySelector('#gnb_my_name, .gnb_id, .MyView-module__link_login___HpHep');
    const bodySnippet = (document.body?.innerText || '').slice(0, 300);
    return {hasLoginBtn, hasProfile, bodySnippet};
}""")
print('로그인버튼:', result['hasLoginBtn'])
print('프로필:', result['hasProfile'])
print('본문:', result['bodySnippet'])
