import os, socket, threading, time
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import pytest, uvicorn
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import delete, select
from backend.core.security import hash_password
from backend.database.connection import SessionLocal
from backend.main import app
from backend.models.analisis import Analisis
from backend.models.log import Log
from backend.models.persona import Persona
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.rol import Rol
from backend.models.usuario import Usuario

BROWSER_OVERRIDE=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")

def find_browser():
    if BROWSER_OVERRIDE and Path(BROWSER_OVERRIDE).is_file(): return Path(BROWSER_OVERRIDE)
    patterns=("AppData/Local/ms-playwright/chromium-*/chrome-win*/chrome.exe", ".cache/ms-playwright/chromium-*/chrome-linux*/chrome", "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium")
    for pattern in patterns:
        matches=sorted(Path.home().glob(pattern),reverse=True)
        if matches: return matches[0]
    return None

def test_real_browser_end_to_end():
    executable=find_browser()
    if executable is None: pytest.skip("Chromium E2E no disponible")
    marker=f"E2E-{uuid4().hex[:10]}"; password=f"VoxTrace-{uuid4().hex}!"; db=SessionLocal(); ids=[]; created_role_ids=[]
    try:
        roles={r.nombre:r for r in db.scalars(select(Rol)).all()}
        for name in ("Administrador","Investigador","Analista"):
            if name not in roles:
                roles[name]=Rol(nombre=name,descripcion=f"Rol temporal {marker}");db.add(roles[name]);db.flush();created_role_ids.append(roles[name].id_rol)
        for name in ("Administrador","Investigador","Analista"):
            u=Usuario(id_rol=roles[name].id_rol,nombre=f"{marker}-{name}",correo=f"{marker.lower()}-{name.lower()}@example.com",password_hash=hash_password(password),estado=True);db.add(u);db.flush();ids.append(u.id_usuario)
        person=Persona(identificador=marker,nombre="Persona E2E",alias="Temporal");db.add(person);db.flush()
        analysis=Analisis(id_usuario=ids[2],ruta_audio_consulta=f"storage/{marker}.wav",nombre_original="consulta-e2e.wav",formato_original="wav",hash_audio_consulta=uuid4().hex,estado="completado");db.add(analysis);db.flush()
        db.add(ResultadoAnalisis(id_analisis=analysis.id_analisis,id_persona=person.id_persona,similitud=79.207,posicion=1,supera_umbral=False))
        for i in range(24): db.add(Log(id_usuario=ids[0],accion="evento_e2e",direccion_ip="127.0.0.1",detalles=f"{marker};item={i}"))
        db.commit(); person_id=person.id_persona; analysis_id=analysis.id_analisis
        sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1];sock.close();server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="error"));thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        base=f"http://127.0.0.1:{port}";console=[];failed=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=str(executable));page=browser.new_page(viewport={"width":1366,"height":768},accept_downloads=True)
            page.on("console",lambda m: console.append(m.text) if m.type=="error" else None);page.on("response",lambda r: failed.append((r.status,r.url)) if r.status>=500 or r.status==404 else None)
            def login(index):
                page.goto(base+"/login");page.fill("#correo",f"{marker.lower()}-{('administrador','investigador','analista')[index]}@example.com");page.fill("#password",password);page.click('button[type="submit"]');page.wait_for_url("**/dashboard")
            def assert_no_page_overflow():
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.set_viewport_size({"width":390,"height":844});page.goto(base+"/dashboard");assert page.url.endswith("/login") or page.locator("h1").count()==0;assert_no_page_overflow();page.set_viewport_size({"width":1366,"height":768})
            page.goto(base+"/login");page.fill("#correo",f"{marker.lower()}-administrador@example.com");page.fill("#password","incorrecta");page.click('button[type="submit"]');expect(page.locator("#form-message")).to_contain_text("incorrectos");console.clear()
            login(0);expect(page.locator("#dashboard-stats")).to_be_visible();assert page.locator("#daily-chart .daily-column").count()==7;action_cards=page.locator(".dashboard-actions .action-card");assert action_cards.count()==4;assert len({round(action_cards.nth(i).bounding_box()["y"]) for i in range(4)})==1;assert page.locator('a[href="/app/usuarios"]').count()==1 and page.locator('a[href="/app/auditoria"]').count()==1;assert_no_page_overflow()
            page.set_viewport_size({"width":1920,"height":1080});page.goto(base+"/dashboard");expect(page.locator("#dashboard-stats")).to_be_visible();assert_no_page_overflow();page.set_viewport_size({"width":1366,"height":768})
            page.goto(base+"/app/personas");page.fill("#person-search",marker);page.click("#search-button");page.wait_for_timeout(300);assert marker in page.locator("#persons-body").inner_text()
            page.goto(base+f"/app/personas/{person_id}/muestras");assert page.locator("#sample-form").count()==1
            page.goto(base+"/app/analizar");page.set_input_files("#analysis-file",{"name":"invalid.txt","mimeType":"text/plain","buffer":b"bad"});page.click("#analysis-submit");assert "Formato no admitido" in page.locator("#analysis-status").inner_text()
            page.goto(base+"/app/historial");page.wait_for_timeout(400);page.fill("#history-search","consulta-e2e");page.click('#history-filters button[type="submit"]');page.wait_for_timeout(300);page.click(f'a[href="/app/historial/{analysis_id}"]');page.wait_for_timeout(300);assert "79.207 / 100" in page.locator("#analysis-general").inner_text();page.click("#view-report");page.wait_for_timeout(300);assert "Nota" in page.locator("#report-content").inner_text() or "probabilidad" in page.locator("#report-content").inner_text()
            with page.expect_download() as download: page.click("#download-pdf")
            assert download.value.suggested_filename==f"voxtrace_analisis_{analysis_id}.pdf"
            page.goto(base+"/app/auditoria");page.wait_for_timeout(300);page.fill("#audit-action","evento_e2e");page.click("#audit-filters .button-primary");page.wait_for_timeout(300);assert "evento_e2e" in page.locator("#audit-body").inner_text();page.click("#audit-next")
            page.wait_for_timeout(200);main=page.locator(".main-content");sidebar_box=page.locator("#primary-sidebar").bounding_box();assert main.evaluate("element => element.scrollHeight > element.clientHeight");main.evaluate("element => element.scrollTop = element.scrollHeight");assert page.evaluate("window.scrollY") == 0;assert page.locator("#primary-sidebar").bounding_box()["y"] == pytest.approx(sidebar_box["y"])
            page.set_viewport_size({"width":820,"height":1180});page.goto(base+"/dashboard");expect(page.locator("#dashboard-stats")).to_be_visible();expect(page.locator("#mobile-menu-button")).to_be_visible();page.click("#mobile-menu-button");expect(page.locator("#primary-sidebar")).to_have_class("sidebar is-open");expect(page.locator("#logout-button")).to_be_visible();assert_no_page_overflow();page.click("#mobile-menu-button")
            page.set_viewport_size({"width":390,"height":844});page.goto(base+"/dashboard");expect(page.locator("#dashboard-stats")).to_be_visible();assert_no_page_overflow();expect(page.locator("#mobile-menu-button")).to_be_visible();page.click("#mobile-menu-button");expect(page.locator("#primary-sidebar")).to_have_class("sidebar is-open");page.click('#primary-sidebar a[href="/app/personas"]');page.wait_for_url("**/app/personas");expect(page.locator("#primary-sidebar")).to_have_class("sidebar");assert_no_page_overflow()
            for route in ("/app/personas/nueva",f"/app/personas/{person_id}/muestras","/app/analizar","/app/historial",f"/app/historial/{analysis_id}","/app/usuarios","/app/auditoria"):
                page.goto(base+route);page.wait_for_timeout(150);assert_no_page_overflow()
                if route.endswith(str(analysis_id)): assert "79.207 / 100" in page.locator("#analysis-general").inner_text()
            page.set_viewport_size({"width":1366,"height":768});page.goto(base+"/dashboard")
            page.click("#logout-button");page.wait_for_url("**/login")
            login(1);assert page.locator('a[href="/app/usuarios"]').count()==0;assert page.goto(base+"/app/usuarios").status==403;console.clear()
            page.context.clear_cookies();login(2);assert page.locator('a[href="/app/auditoria"]').count()==0;assert page.goto(base+"/app/auditoria").status==403;console.clear()
            browser.close()
        server.should_exit=True;thread.join(10)
        assert not console,console;assert not failed,failed
    finally:
        db.rollback();db.close();cleanup=SessionLocal()
        try:
            cleanup.execute(delete(Log).where(Log.id_usuario.in_(ids)))
            cleanup.execute(delete(ResultadoAnalisis).where(ResultadoAnalisis.id_analisis.in_(select(Analisis.id_analisis).where(Analisis.id_usuario.in_(ids)))))
            cleanup.execute(delete(Analisis).where(Analisis.id_usuario.in_(ids)))
            cleanup.execute(delete(Persona).where(Persona.identificador.like(f"{marker}%")))
            cleanup.execute(delete(Usuario).where(Usuario.id_usuario.in_(ids)))
            if created_role_ids: cleanup.execute(delete(Rol).where(Rol.id_rol.in_(created_role_ids)))
            cleanup.commit()
        finally: cleanup.close()
