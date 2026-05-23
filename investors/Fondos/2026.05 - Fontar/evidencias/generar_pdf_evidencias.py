#!/usr/bin/env python3
"""Genera el PDF narrativo de evidencias FONTAR desde HTML + Chrome headless."""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
HTML_OUT = BASE / "Aikiu_Evidencias_FONTAR.html"
PDF_OUT = BASE / "Aikiu_Evidencias_FONTAR.pdf"

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Aikiu — Evidencias de desarrollo (FONTAR)</title>
<style>
  @page { size: A4; margin: 22mm 20mm; }
  * { box-sizing: border-box; }
  body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11.5pt;
    line-height: 1.55;
    color: #1a1a1a;
    max-width: 170mm;
    margin: 0 auto;
    padding: 0;
  }
  h1, h2, h3 { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.25; }
  h1 { font-size: 26pt; margin: 0 0 8px; font-weight: 600; }
  h2 { font-size: 16pt; margin: 28px 0 10px; color: #2c5282; page-break-after: avoid; }
  h3 { font-size: 12.5pt; margin: 18px 0 8px; color: #444; page-break-after: avoid; }
  p { margin: 0 0 12px; text-align: justify; }
  .cover {
    page-break-after: always;
    min-height: 240mm;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 20mm 0;
  }
  .cover .sub { font-size: 14pt; color: #555; margin-top: 12px; font-style: italic; }
  .cover .meta { margin-top: 48px; font-size: 11pt; color: #666; font-family: sans-serif; }
  .chapter { page-break-before: always; }
  .chapter:first-of-type { page-break-before: auto; }
  .lead { font-size: 13pt; color: #333; font-style: italic; border-left: 3px solid #5288c1; padding-left: 14px; margin: 16px 0 20px; }
  .note {
    background: #f8f6f0;
    border-radius: 6px;
    padding: 12px 14px;
    margin: 14px 0;
    font-size: 10.5pt;
    font-family: sans-serif;
  }
  .note strong { color: #2c5282; }
  .figure { margin: 20px 0; page-break-inside: avoid; }
  .figure-caption {
    font-size: 10pt;
    color: #555;
    font-family: sans-serif;
    margin-top: 8px;
    text-align: center;
  }
  .toc { page-break-after: always; }
  .toc li { margin: 6px 0; }
  .toc a { color: inherit; text-decoration: none; }
  ul { margin: 0 0 12px 20px; }
  li { margin: 4px 0; }

  /* Telegram mini mockup */
  .tg-wrap {
    border: 1px solid #d0d5db;
    border-radius: 8px;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 13px;
    max-width: 100%;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }
  .tg-bar {
    background: linear-gradient(#ececec, #d8d8d8);
    padding: 6px 10px;
    font-size: 11px;
    color: #555;
    text-align: center;
    border-bottom: 1px solid #ccc;
  }
  .tg-body { display: flex; min-height: 280px; }
  .tg-side {
    width: 28%;
    background: #fff;
    border-right: 1px solid #e7eaed;
    padding: 8px;
  }
  .tg-side .chat-active {
    background: #4ea1d6;
    color: #fff;
    padding: 8px;
    border-radius: 6px;
    font-size: 11px;
  }
  .tg-side .chat-other { padding: 8px; font-size: 11px; color: #666; }
  .tg-main {
    flex: 1;
    background: linear-gradient(135deg, #c4d6a2, #8eb066);
    display: flex;
    flex-direction: column;
  }
  .tg-head {
    background: #fff;
    padding: 8px 12px;
    border-bottom: 1px solid #e7eaed;
    font-weight: 600;
    font-size: 13px;
  }
  .tg-head span { font-weight: 400; font-size: 11px; color: #7a8a99; }
  .tg-msgs { flex: 1; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
  .pill-date {
    align-self: center;
    background: rgba(95,130,60,0.6);
    color: #fff;
    font-size: 10px;
    padding: 2px 10px;
    border-radius: 10px;
  }
  .b-out { align-self: flex-end; background: #effdde; padding: 8px 10px; border-radius: 12px 12px 4px 12px; max-width: 85%; box-shadow: 0 1px 1px rgba(0,0,0,0.06); }
  .b-in { align-self: flex-start; background: #fff; padding: 8px 10px; border-radius: 12px 12px 12px 4px; max-width: 85%; box-shadow: 0 1px 1px rgba(0,0,0,0.06); }
  .b-alert {
    align-self: flex-start;
    background: #fff;
    padding: 10px 12px;
    border-radius: 12px;
    border-left: 4px solid #f1c40f;
    max-width: 90%;
    font-size: 12px;
  }
  .b-alert.orange { border-left-color: #e67e22; }
  .b-alert.red { border-left-color: #e74c3c; }
  .b-alert.warn { border-left-color: #d39e00; }
  .tg-foot {
    background: #fff;
    padding: 8px 12px;
    border-top: 1px solid #e7eaed;
    font-size: 12px;
    color: #95a4ad;
  }
  .two-col { display: flex; gap: 16px; flex-wrap: wrap; }
  .two-col > * { flex: 1; min-width: 45%; }
  pre {
    font-size: 9pt;
    background: #f4f4f4;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-family: Menlo, monospace;
  }
  .closing { page-break-before: always; }
  @media print {
    body { max-width: none; }
    a { color: inherit; }
  }
</style>
</head>
<body>

<section class="cover">
  <h1>Aikiu</h1>
  <p class="sub">Una compañía de voz para Marta, y tranquilidad para su familia</p>
  <p style="margin-top: 32px; font-size: 12pt;">
    Este documento reúne evidencias del desarrollo tecnológico del prototipo Aikiu,
    presentado en el marco de la convocatoria FONTAR — Start Up de Base Tecnológica (TRL 3–4).
  </p>
  <p class="meta">
    Proyecto: aikiu · Eje: Salud · Ciudad de Buenos Aires<br>
    Usuaria piloto: Marta, 83 años · Asistente: Clara<br>
    Fecha de elaboración: mayo 2026 · Estado: TRL 4
  </p>
</section>

<section class="toc">
  <h2>Índice</h2>
  <ol>
    <li><a href="#intro">Por qué existe Aikiu</a></li>
    <li><a href="#manana">Una mañana con Clara</a></li>
    <li><a href="#charla">Charlar, como con un familiar</a></li>
    <li><a href="#mundo">Preguntas del día a día</a></li>
    <li><a href="#cuidado">Cuando Marta necesita contención</a></li>
    <li><a href="#familia">La familia, siempre al tanto</a></li>
    <li><a href="#aprende">Clara aprende cada noche</a></li>
    <li><a href="#resiliencia">Si algo falla, la conversación sigue</a></li>
    <li><a href="#cierre">Lo que deja este piloto</a></li>
  </ol>
</section>

<section id="intro" class="chapter">
  <h2>1. Por qué existe Aikiu</h2>
  <p class="lead">
    Marta vive sola en Buenos Aires. Su hijo Germán y sus nietos Lao y Cata la quieren,
    pero no siempre pueden estar. Aikiu no reemplaza a la familia: la acerca.
  </p>
  <p>
    Aikiu es un asistente de voz que funciona por Telegram, en el celular que Marta ya usa.
    No hay que comprar un botón de pánico ni instalar otra aplicación. Habla con Clara —
    una voz cálida, en español rioplatense — y la familia recibe señales cuando algo
    merece atención, sin invadir la intimidad de Marta con cámaras ni llamadas constantes.
  </p>
  <p>
    Las pantallas que siguen muestran cómo se ve esa experiencia en Telegram Web,
    el mismo canal que usa la usuaria piloto. Los diálogos son representativos del
    comportamiento verificado del sistema durante el piloto y las pruebas automatizadas.
  </p>
</section>

<section id="manana" class="chapter">
  <h2>2. Una mañana con Clara</h2>
  <p>
    A las 8:30, sin que Marta tenga que escribir nada, Clara la saluda. Le dice qué día es —
    para ayudarla a ubicarse en la semana — y cómo está el tiempo en Olivos, donde vive.
    Después pregunta, con naturalidad, cómo amaneció.
  </p>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-bar">Telegram Web — Clara</div>
      <div class="tg-body">
        <div class="tg-side">
          <div class="chat-active">Clara · Buenos días…</div>
          <div class="chat-other" style="margin-top:6px;">aikiu — Familia</div>
        </div>
        <div class="tg-main">
          <div class="tg-head">Clara <span>en línea</span></div>
          <div class="tg-msgs">
            <div class="pill-date">hoy</div>
            <div class="b-in">🎤 «Hola Marta, soy Clara. Hoy es miércoles 20 de mayo. Hoy en Olivos hay 16 grados, con sensación de 14. ¿Cómo amaneciste hoy?»</div>
            <div class="b-out">Buenos días Clarita, durmí bárbaro</div>
            <div class="b-in">Qué bueno escuchar eso. ¿Vas a desayunar algo rico?</div>
          </div>
          <div class="tg-foot">Mensaje</div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 1 — Saludo matutino proactivo con fecha y temperatura.</p>
  </div>
  <p>
    Si el servicio de clima no responde, el saludo llega igual, sin temperatura pero con el
    mismo cariño. La idea es que Marta sienta que alguien la espera a la mañana, no que
    un sistema le manda un recordatorio frío.
  </p>
</section>

<section id="charla" class="chapter">
  <h2>3. Charlar, como con un familiar</h2>
  <p>
    Marta puede escribir o mandar una nota de voz. Clara responde en el mismo medio:
    texto con texto, voz con voz. Las respuestas son cortas, cálidas, sin listas ni símbolos
    raros — pensadas para ser escuchadas, no leídas en una pantalla complicada.
  </p>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-bar">Telegram Web — Clara</div>
      <div class="tg-body">
        <div class="tg-side"><div class="chat-active">Clara</div></div>
        <div class="tg-main">
          <div class="tg-head">Clara</div>
          <div class="tg-msgs">
            <div class="pill-date">hoy</div>
            <div class="b-out">Hola Clara</div>
            <div class="b-in">Hola Marta, ¿cómo estás? Qué lindo escucharte temprano.</div>
            <div class="b-out">Bien, hoy quiero hacer un guiso</div>
            <div class="b-in">Qué buena idea. ¿De qué lo vas a hacer, de lentejas o de pollo?</div>
          </div>
          <div class="tg-foot">Mensaje</div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 2 — Conversación por texto: mismo medio, tono cercano.</p>
  </div>
  <p>
    En el piloto, Marta charla de sus plantas del balcón, del tango, de sus nietos.
    Clara no corrige si confunde un nombre; entiende el contexto y sigue la conversación
    con respeto.
  </p>
</section>

<section id="mundo" class="chapter">
  <h2>4. Preguntas del día a día</h2>
  <p>
    A veces Marta pregunta por el tiempo, el dólar o las noticias. Esas respuestas no las
    inventa Clara: el sistema consulta fuentes públicas (clima, cotización, titulares) y
    después las dice con palabras simples. Así se evita que una persona mayor reciba un
    dato inventado sobre algo importante.
  </p>

  <h3>El clima en Olivos</h3>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-body" style="min-height:200px">
        <div class="tg-side"><div class="chat-active">Clara</div></div>
        <div class="tg-main">
          <div class="tg-head">Clara</div>
          <div class="tg-msgs">
            <div class="b-out">¿Qué tiempo hace hoy?</div>
            <div class="b-in">Hoy en Olivos hay 16 grados, con sensación de 14. Está parcialmente nublado, así que si salís llevate un saquito.</div>
          </div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 3 — Consulta de clima con datos reales.</p>
  </div>

  <h3>El dólar y las noticias</h3>
  <p>
    Lo mismo ocurre con el dólar blue y oficial, o con los titulares del día: Clara resume
    sin entrar en política ni en detalles que puedan angustiar. Si Marta pregunta por un
    conflicto lejano, responde con una frase breve y vuelve a algo cotidiano — sus plantas,
    la cocina, la familia.
  </p>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-body" style="min-height:180px">
        <div class="tg-main" style="width:100%">
          <div class="tg-msgs">
            <div class="b-out">¿A cuánto está el dólar?</div>
            <div class="b-in">El dólar blue está a 1.245 comprador y 1.265 vendedor. El oficial cotiza a 980 y 1.000.</div>
            <div class="b-out">¿Qué noticias hay hoy?</div>
            <div class="b-in">Hoy los titulares principales son: acuerdo con la UIA, censo agropecuario, fútbol el domingo y suba de nafta. ¿De cuál querés que te cuente más?</div>
          </div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 4 — Dólar y noticias sin alucinaciones del modelo.</p>
  </div>
</section>

<section id="cuidado" class="chapter">
  <h2>5. Cuando Marta necesita contención</h2>
  <p>
    Detrás de cada charla, el sistema observa con cuidado — sin que Marta lo note — si
    hay señales de soledad, tristeza o malestar. No es un diagnóstico médico: es una manera
    de avisar a la familia a tiempo, con calma y contexto.
  </p>
  <p>
    Marta nunca ve códigos ni alertas técnicas. Solo escucha a Clara, que la contiene.
    Al mismo tiempo, Germán, Lao y Cata reciben un mensaje en el bot familiar compartido.
  </p>

  <h3>Cuando dice que se siente sola</h3>
  <div class="two-col">
    <div class="figure">
      <div class="tg-wrap">
        <div class="tg-bar">Marta ↔ Clara</div>
        <div class="tg-body" style="min-height:160px">
          <div class="tg-main" style="width:100%">
            <div class="tg-msgs">
              <div class="b-out">Me siento muy sola hoy</div>
              <div class="b-in">Marta, lamento mucho que te sientas así. ¿Querés que charlemos un rato?</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="figure">
      <div class="tg-wrap">
        <div class="tg-bar">aikiu — Familia</div>
        <div class="tg-body" style="min-height:160px">
          <div class="tg-main" style="width:100%">
            <div class="tg-msgs">
              <div class="b-alert">
                <strong>🟡 Marta mencionó algo que podría indicar que no está del todo bien.</strong><br><br>
                Marta dijo: «Me siento muy sola hoy»<br>
                Clara respondió con contención y propuso conversar.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <p class="figure-caption">Figura 5 — Señal amarilla: soledad. La familia puede llamar sin alarmar a Marta.</p>

  <h3>Cuando el malestar es más intenso</h3>
  <p>
    Si Marta llora, habla de dolor que no pasa o de una caída reciente, la alerta sube de
    nivel. Clara le sugiere siempre consultar al médico y avisar a Germán — sin minimizar
    lo que siente.
  </p>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-bar">aikiu — Familia</div>
      <div class="tg-body" style="min-height:140px">
        <div class="tg-main" style="width:100%">
          <div class="tg-msgs">
            <div class="b-alert orange">
              <strong>🟠 Marta parece estar angustiada ahora mismo.</strong><br><br>
              «Estoy llorando, me duele mucho la espalda hace tres días»<br>
              Sugerencia: contacto en las próximas horas; evaluar consulta médica.
            </div>
          </div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 6 — Señal naranja: malestar sostenido o dolor.</p>
  </div>

  <h3>Emergencia: una prueba controlada</h3>
  <div class="note">
    <strong>Nota para el evaluador.</strong> La siguiente pantalla corresponde a una
    <strong>simulación técnica</strong> del nivel más alto de alerta (caída con imposibilidad
    de levantarse). Se realizó para verificar que el mensaje llega de inmediato a la familia
    y que Clara responde con instrucciones claras (no moverse, llamar a Germán o al 107).
    No documenta un evento real de la usuaria piloto en esa fecha.
  </div>
  <div class="two-col">
    <div class="figure">
      <div class="tg-wrap">
        <div class="tg-bar">Marta ↔ Clara (simulación)</div>
        <div class="tg-body" style="min-height:140px">
          <div class="tg-main" style="width:100%">
            <div class="tg-msgs">
              <div class="b-out">Me caí, no me puedo levantar</div>
              <div class="b-in">Marta, no te muevas. Llamá a Germán o al 107. Le aviso a tu familia ahora.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="figure">
      <div class="tg-wrap">
        <div class="tg-bar">aikiu — Familia (simulación)</div>
        <div class="tg-body" style="min-height:140px">
          <div class="tg-main" style="width:100%">
            <div class="tg-msgs">
              <div class="b-alert red">
                <strong>🔴 ALERTA: Marta puede necesitar ayuda urgente.</strong><br><br>
                Posible caída. Acción inmediata: llamar a Marta; si no responde, acudir al domicilio.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <p class="figure-caption">Figura 7 — Simulación de emergencia (nivel 3), sin cooldown entre alertas.</p>
</section>

<section id="familia" class="chapter">
  <h2>6. La familia, siempre al tanto</h2>

  <h3>Si Marta no escribe en varias horas</h3>
  <p>
    No siempre el silencio es malo: a veces Marta está bien y simplemente no abrió Telegram.
    Aun así, si pasan varias horas sin mensajes, la familia recibe un aviso suave — no
    una alarma — para que alguien pueda llamarla.
  </p>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-bar">aikiu — Familia</div>
      <div class="tg-body" style="min-height:120px">
        <div class="tg-main" style="width:100%">
          <div class="tg-msgs">
            <div class="b-alert warn">
              <strong>⚠️ Sin noticias de Marta</strong><br>
              Lleva 5 horas sin enviar mensajes. Último mensaje: 06:42 del 20/05.<br>
              Puede estar bien y no haber usado el bot, pero vale verificar.
            </div>
          </div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 8 — Inactividad: tono no alarmista, una alerta por día como máximo.</p>
  </div>

  <h3>Germán le manda un mensaje a Marta</h3>
  <p>
    Desde el bot familiar, cualquier integrante registrado puede escribir o hablar.
    Clara se lo transmite a Marta con el nombre real — «Germán te manda a decir…» —
    no como un número desconocido.
  </p>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-body" style="min-height:200px">
        <div class="tg-main" style="width:100%">
          <div class="tg-msgs">
            <div class="b-out" style="align-self:flex-end;background:#e3f2fd">/mensaje → Mamá, salgo temprano, ¿te paso a las 18?</div>
            <div class="b-in">Listo, le mandé a Marta: «Germán te manda a decir: …»</div>
            <div class="b-in" style="margin-top:8px;border-left:3px solid #f6a623;padding-left:8px">En el chat de Marta: Germán te manda a decir… → «Sí, tengo galletas recién hechas»</div>
          </div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 9 — Puente familiar con nombre, no con usuario de Telegram.</p>
  </div>

  <h3>Configurar a Clara sin tocar archivos</h3>
  <p>
    Germán puede ver el perfil completo de Marta, editar secciones (gustos, familia, salud)
    y ver quién más recibe alertas — todo desde Telegram, con mensajes claros y sin
    comandos de computadora.
  </p>
  <p>
    Comandos disponibles: <em>/perfil</em>, <em>/editar</em>, <em>/mensaje</em>,
    <em>/nombre</em>, <em>/suscriptores</em>, <em>/ayuda</em>.
  </p>
</section>

<section id="aprende" class="chapter">
  <h2>7. Clara aprende cada noche</h2>
  <p>
    Cada noche, cuando Marta ya descansó, el sistema relee la charla del día — no para
    espiar, sino para recordar: qué le gustó, qué la entristeció, qué temas conviene
    retomar mañana. Eso se guarda en su perfil, y al día siguiente Clara lo tiene en cuenta.
  </p>
  <p>Ejemplo de lo que puede aparecer después de un día de conversación:</p>
  <pre>## Aprendizajes
- Marta cocina guisos los días fríos; le gusta el de lentejas. (20/05/2026)
- Las plantas del balcón están floreciendo. (20/05/2026)
- Mencionó dolor de espalda desde hace tres días. (20/05/2026)</pre>
  <p>
    La familia no tiene que programar nada: el sistema mejora solo con el uso, siempre
    bajo supervisión humana y con la posibilidad de corregir el perfil desde el bot familiar.
  </p>
</section>

<section id="resiliencia" class="chapter">
  <h2>8. Si algo falla, la conversación sigue</h2>
  <p>
    Si un servicio externo (clima, noticias) no responde, Clara no se queda muda ni inventa
    datos. Dice con honestidad que ahora no puede ver el clima y propone seguir charlando.
    La confianza de Marta no depende de que todo funcione perfecto siempre.
  </p>
  <div class="figure">
    <div class="tg-wrap">
      <div class="tg-body" style="min-height:120px">
        <div class="tg-main" style="width:100%">
          <div class="tg-msgs">
            <div class="b-out">¿Qué tiempo hace hoy?</div>
            <div class="b-in">Ay Marta, ahora no puedo ver el clima. ¿Querés que probemos en un ratito? Contame cómo amaneciste.</div>
          </div>
        </div>
      </div>
    </div>
    <p class="figure-caption">Figura 10 — Degradación elegante ante fallo de API.</p>
  </div>
</section>

<section id="cierre" class="chapter closing">
  <h2>9. Lo que deja este piloto</h2>
  <p>
    Durante el piloto, Marta — 83 años, vive sola en Buenos Aires — usó Aikiu de forma
    sostenida. Su hijo Germán configuró el perfil y recibió alertas cuando el sistema
    detectó momentos de soledad o malestar que en una llamada breve podrían pasar
    desapercibidos.
  </p>
  <p>
    El prototipo cuenta con <strong>113 pruebas automatizadas</strong> que verifican
    alertas, conversación, herramientas de clima y dólar, análisis nocturno y
    comportamiento del bot familiar. Opera en TRL 4: validado en entorno real controlado,
    listo para escalar validación con más familias e institución gerontológica (objetivo TRL 6).
  </p>
  <p>
    Aikiu no vende hardware ni miedo. Ofrece compañía cotidiana para quien envejece en su casa,
    y una red familiar que puede actuar con información oportuna — con respeto, con calidez,
    con la tecnología al servicio del cuidado humano.
  </p>
  <p class="meta" style="margin-top: 40px; font-family: sans-serif; font-size: 10pt; color: #666;">
    Documento de evidencias · Proyecto aikiu · FONTAR 2026<br>
    Contacto: germanv@gmail.com · Germán Villamarín
  </p>
</section>

</body>
</html>
"""


def main():
    HTML_OUT.write_text(HTML, encoding="utf-8")
    print(f"HTML: {HTML_OUT}")

    if not CHROME.exists():
        print("Chrome no encontrado. Abrí el HTML y usá Archivo → Imprimir → Guardar como PDF.", file=sys.stderr)
        return 1

    url = HTML_OUT.as_uri()
    cmd = [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_OUT}",
        url,
    ]
    subprocess.run(cmd, check=True)
    print(f"PDF: {PDF_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
