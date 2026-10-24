from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_base_contains_single_accessible_mobile_navigation() -> None:
    template = (ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")
    assert template.count('id="primary-sidebar"') == 1
    assert 'aria-controls="primary-sidebar"' in template
    assert 'id="mobile-menu-button"' in template
    assert 'id="sidebar-overlay"' in template


def test_responsive_css_covers_mobile_and_table_overflow() -> None:
    css = (ROOT / "frontend/static/css/voxtrace.css").read_text(encoding="utf-8")
    assert "@media(max-width:1024px)" in css
    assert "overflow-x:auto" in css
    assert ".candidate-grid{grid-template-columns:1fr}" in css
    assert ".sidebar.is-open" in css


def test_desktop_sidebar_and_main_have_independent_vertical_scrolling() -> None:
    css = (ROOT / "frontend/static/css/layout.css").read_text(encoding="utf-8")
    assert "grid-template-columns: 250px minmax(0, 1fr)" in css
    assert "position: sticky" in css
    assert "height: 100vh" in css
    assert "overflow-y: auto" in css
    assert ".main-content" in css


def test_tablet_and_mobile_use_a_drawer_without_reducing_content_width() -> None:
    css = (ROOT / "frontend/static/css/layout.css").read_text(encoding="utf-8")
    assert "@media (max-width: 1024px)" in css
    assert "position: fixed" in css
    assert "calc(100vw - 32px)" in css
    assert "height: calc(100dvh - 58px)" in css


def test_dashboard_charts_stack_without_horizontal_overflow() -> None:
    css = (ROOT / "frontend/static/css/dashboard.css").read_text(encoding="utf-8")
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in css
    assert "@media(max-width:1024px)" in css
    assert ".dashboard-chart-grid{grid-template-columns:1fr}" in css
    assert "@media(max-width:600px)" in css
    assert ".summary-grid{grid-template-columns:1fr}" in css


def test_dashboard_quick_actions_are_compact_and_responsive() -> None:
    template = (ROOT / "frontend/templates/dashboard.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend/static/css/dashboard.css").read_text(encoding="utf-8")
    assert 'class="card-grid dashboard-actions"' in template
    assert ".dashboard-actions{grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}" in css
    assert ".dashboard-actions .action-card{display:flex" in css
    assert "min-height:68px" in css
    assert "@media(max-width:1024px){.dashboard-actions{grid-template-columns:repeat(2,minmax(0,1fr))}" in css
    assert "repeat(auto-fit,minmax(min(145px,100%),1fr))" in css


def test_mobile_navigation_closes_after_selection() -> None:
    script = (ROOT / "frontend/static/js/app.js").read_text(encoding="utf-8")
    assert 'querySelectorAll("a")' in script
    assert 'setMenu(false)' in script
    assert 'event.key==="Escape"' in script
    assert "window.innerWidth>1024" in script
