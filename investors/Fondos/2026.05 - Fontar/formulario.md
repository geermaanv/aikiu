# Formulario FONTAR — Proyectos Innovadores Start Up de Base Tecnológica (TRL 3-4)

**Estado**: borrador de trabajo
**Convocatoria**: Proyectos Innovadores Start Up de Base Tecnológica TRL 3-4
**Última edición**: 2026-05-20

---

## 1. Identificación del Proyecto

- **Clasificación de convocatorias**: Proyectos Innovadores Start Up de Base Tecnológica TRL 3-4.
- **Nombre del Proyecto**: aikiu.
- **Eje Estratégico**: Salud.
- **Institución Beneficiaria**: *(pendiente)*.
- **Ubicación**: Belgrano, Comuna 13, Ciudad de Buenos Aires.
- **CUIT**: 20218342222.
- **Responsable legal**: Germán Osvaldo Villamarín.
- **Correo de contacto**: germanv@gmail.com.
- **Presupuesto total del proyecto**: 97.500 USD.
- **ANR solicitado al FONTAR (80%)**: 78.000 USD.
- **Contraparte del equipo beneficiario (20%)**: 19.500 USD — aportados en especie por los tres miembros del equipo: Germán Villamarín, Ariel Brizi y Nicolás Gonzalez (horas de trabajo e infraestructura existente).
- **Plazo de ejecución**: 15 meses.

### Objetivo General

Validar y escalar **aikiu**, un asistente de voz por Telegram que permite saber, día a día, que el adulto mayor que vive solo está bien, combinando chequeos automáticos de actividad, análisis semántico de cada conversación, recordatorios proactivos y un análisis nocturno que aprende y mejora el acompañamiento de forma autónoma. Toda la operación es **supervisada y configurada por la familia**, que recibe alertas tempranas ante angustia, inactividad o aislamiento. Opera sobre el smartphone existente —sin hardware adicional— y es **gratuito o de costo mínimo para las familias** gracias a un modelo de **sponsors institucionales**.

---

## 2. Innovación

**¿Qué hace única a la solución respecto de otras disponibles en el mercado?**

- **Arquitectura de Fricción Cero**: A diferencia de los sistemas de teleasistencia tradicionales que requieren la compra e instalación de hardware específico (botones de pánico, sensores de movimiento o cámaras), aikiu funciona sobre la infraestructura que el adulto mayor ya posee y domina: su propio smartphone y el servicio de mensajería Telegram. Esto elimina las barreras de costo inicial y de resistencia al cambio tecnológico.
- **Monitoreo Proactivo vs. Reactivo**: La mayoría de las soluciones del mercado son reactivas (esperan a que el usuario presione un botón ante una emergencia). aikiu es proactivo: inicia conversaciones naturales para verificar el bienestar y utiliza modelos de lenguaje avanzados (Llama-3.3) para detectar de forma automatizada estados de apatía, tristeza o desorientación a través del análisis semántico.
- **Privacidad por Diseño**: Mientras que otros asistentes comerciales procesan datos íntegros en la nube, aikiu está diseñando una capa local de ofuscación que anonimiza datos críticos antes de enviarlos a los modelos de inferencia, garantizando la seguridad de la información sensible del usuario.
- **Modelo de Eficiencia de Costos**: Al no depender de servidores propios y utilizar infraestructuras serverless y APIs de alta eficiencia como Groq, el costo operativo por usuario es marginal. Esto permite ofrecer una solución gratuita para las familias, democratizando el acceso a tecnología de cuidado de última generación que actualmente solo está disponible en segmentos de alto poder adquisitivo.
- **Detección Gradual de Angustia (DISTRESS_LEVEL)**: El sistema no solo detecta emergencias médicas, sino que clasifica el sentimiento en una escala del 0 al 3. Esto permite que la familia reciba alertas tempranas sobre el deterioro del estado anímico o el aislamiento social, actuando preventivamente antes de que ocurra una crisis de salud física.
- **Aprendizaje Diario Autónomo**: cada noche, un análisis automático del registro del día extrae aprendizajes nuevos sobre el adulto mayor (gustos, rutinas, temas sensibles) y detecta patrones problemáticos en la conversación, actualizando el perfil del asistente sin intervención técnica. El sistema mejora solo con el uso.
- **Supervisión Familiar como Eje Central**: a diferencia de otros asistentes que tratan al usuario como única audiencia, aikiu coloca a la red familiar como supervisora del cuidado. La familia configura el perfil, edita reglas de comportamiento, recibe alertas tempranas y puede enviar mensajes que el asistente transmite al adulto mayor — todo a través de un bot familiar compartido en Telegram.
- **Pre-Routing Determinístico (anti-alucinaciones)**: para datos factuales (clima, cotizaciones, noticias), aikiu no depende de la generación creativa del LLM. Un motor de pre-routing detecta el tipo de consulta y la deriva a fuentes oficiales (wttr.in, dolarapi.com, RSS de La Nación), garantizando información veraz y mitigando el riesgo de alucinaciones en un contexto donde el usuario es un adulto mayor que podría no advertir respuestas incorrectas.

---

## 3. Relevancia de la Problemática / Oportunidad Detectada

**Problemática que atiende**: El proyecto aborda la "Epidemia de Soledad" y el aislamiento social de los adultos mayores que viven solos. Actualmente, las familias enfrentan una brecha de cuidado: la imposibilidad de monitorear el bienestar emocional y físico de sus mayores durante la jornada laboral sin recurrir a soluciones invasivas o costosas. Las alternativas actuales (cámaras de seguridad o botones de pánico) presentan alta resistencia por parte del usuario, son reactivas y no resuelven la necesidad de acompañamiento y estímulo cognitivo diario.

**Qué problema resuelve**: aikiu transforma el smartphone del adulto mayor en un sensor proactivo de bienestar a través de la voz. Resuelve el problema de la incertidumbre familiar (¿está bien?, ¿tomó la medicación?, ¿está angustiado?) y la falta de acompañamiento del usuario. Mediante el análisis semántico de conversaciones naturales, el sistema detecta de forma automática niveles de apatía o distress que suelen pasar desapercibidos en llamadas telefónicas breves, permitiendo intervenciones preventivas antes de que se conviertan en crisis de salud.

**Por qué es relevante**: El envejecimiento poblacional es una tendencia irreversible que presiona los sistemas de salud. El cuidado preventivo en el hogar reduce drásticamente las internaciones de emergencia por cuadros de deshidratación, desorientación o accidentes domésticos vinculados al deterioro anímico. Además, el proyecto democratiza el acceso a la "Silver Economy", permitiendo que familias de cualquier nivel socioeconómico accedan a una tecnología de punta que hoy es prohibitiva por costos de hardware.

**Impacto Regional y Nacional**: El impacto es de escala nacional. Según el Censo 2022 del INDEC, el **16,2% de la población argentina tiene 60 años o más** y la **población de 65+ pasó del 10,6% (2010) al 12,0% (2022), proyectándose al 16,4% para 2040** [INDEC, *Dosier estadístico — La transformación de la población argentina*, octubre 2025]. Hay alta concentración de adultos mayores viviendo solos en centros urbanos. Al ser una solución basada íntegramente en software y canales existentes (Telegram), aikiu tiene la capacidad de despliegue inmediato en todo el territorio argentino, con potencial de exportación regional a otros países de habla hispana que enfrentan transiciones demográficas similares.

---

## 4. Nivel actual de desarrollo tecnológico (TRL)

**TRL 4**: Validado en entorno controlado. Prototipo funcional con Whisper, Llama-3.3 y edge-tts.

**Logros**: Algoritmo de angustia (DISTRESS_LEVEL), 111 tests de estabilidad y validación con usuaria piloto real. Software original en Python.

### Estado actual de la tecnología (detalle)

**Fase actual**: TRL 4. Se ha superado la prueba de concepto en laboratorio y se dispone de un prototipo funcional integrado que opera en un entorno real controlado.

**Avances logrados**:

- **Arquitectura Core**: Motor modular en Python que integra STT (Groq Whisper), LLM (Llama-3.3-70b) y TTS (edge-tts), con latencia de respuesta mínima para una interacción fluida.
- **Motor de Decisiones (DISTRESS_LEVEL)**: Sistema propietario que clasifica cada conversación en una escala 0–3 y dispara alertas automáticas a familiares ante señales de apatía, tristeza o emergencia, con cooldowns por nivel para evitar fatiga de alertas.
- **Aprendizaje Nocturno Autónomo**: Job programado que cada noche analiza el log del día, extrae aprendizajes nuevos sobre el adulto mayor evitando duplicados y detecta patrones problemáticos, actualizando el perfil del asistente sin intervención técnica.
- **Chequeos de Actividad e Inactividad**: Verificaciones automáticas dos veces por día (configurables) que disparan alerta a la familia si el adulto mayor no envió mensajes dentro del umbral definido.
- **Bot Familiar (Supervisión)**: Segundo bot de Telegram compartido por la familia, que permite configurar el perfil, editar reglas, recibir alertas y enviar mensajes que el asistente transmite al adulto mayor preservando el medio (voz o texto).
- **Pre-Routing Determinístico**: Módulo `core/tools.py` que intercepta consultas factuales (clima, dólar, noticias) antes de invocar al LLM y las deriva a APIs oficiales (wttr.in, dolarapi.com, RSS de La Nación), evitando alucinaciones y degradando con elegancia ante fallos de API externa.
- **Validación de Campo**: Uso diario sostenido por una usuaria piloto (Marta, 83 años), validando la aceptación de la interfaz de voz y la utilidad de las herramientas integradas (clima, noticias y cotizaciones).
- **Calidad de Software**: Cobertura de 111 tests automatizados (pytest) que aseguran la estabilidad de la lógica de alertas, el análisis nocturno, la persistencia de la sesión, el manejo de temas sensibles y la supervisión familiar.
- **Infraestructura**: Arquitectura serverless de bajo costo, sin hardware propietario, lo que permite el acceso gratuito al usuario final.

### Propiedad intelectual

No cuenta con propiedad intelectual registrada ni en trámite.

---

## 5. Propuesta de Valor

- **Asistencia de Fricción Cero**: Acompañamiento 24/7 sin requerir compra, instalación o aprendizaje de hardware nuevo, operando sobre el smartphone y la app de mensajería que el adulto mayor ya utiliza.
- **Detección Proactiva de Angustia**: IA que analiza semánticamente las conversaciones y detecta niveles de distress (DISTRESS_LEVEL 0-3), permitiendo alertas tempranas ante cuadros de soledad, tristeza o confusión.
- **Chequeos Automáticos de Actividad**: Verificaciones programadas dos veces por día (configurables) que alertan a la familia ante ausencia prolongada de comunicación, sin requerir acción del adulto mayor.
- **Aprendizaje Diario Autónomo**: El asistente mejora con el uso mediante un análisis nocturno que actualiza el perfil del adulto mayor con aprendizajes nuevos y ajustes de conversación, sin intervención técnica.
- **Supervisión y Configuración Familiar**: La red familiar configura el perfil, edita reglas, recibe alertas y envía mensajes que el asistente transmite al adulto mayor — un bot familiar compartido por todos los suscriptores actúa como centro de control y comunicación.
- **Tranquilidad Familiar Automatizada**: Entorno familiar con actualizaciones automáticas y alertas en tiempo real, sin llamadas invasivas constantes.
- **Accesibilidad Económica**: Al eliminar el costo de hardware y optimizar infraestructura serverless, el modelo permite acceso gratuito para las familias mediante sponsors institucionales.
- **Integración de Servicios Útiles**: El asistente resuelve necesidades diarias (clima, noticias, recordatorios de medicación y finanzas) mediante una interfaz puramente conversacional.

### Comparación con otras soluciones del mercado

- **Frente a botones de pánico**: las soluciones tradicionales son reactivas y dependen de hardware costoso y estigmatizante. aikiu es proactivo, sin hardware adicional, y detecta problemas antes de la emergencia.
- **Frente a asistentes comerciales (Alexa, Google Home)**: no están diseñados para cuidado geriátrico ni notifican proactivamente sobre estado anímico. aikiu implementa un algoritmo de clasificación de angustia (DISTRESS_LEVEL) adaptado al lenguaje y necesidades locales.
- **Frente a sistemas con cámaras**: aikiu protege la intimidad con interacción por voz y arquitectura privacy-by-design; al ser software puro, elimina la barrera económica.
- **Monitoreo Proactivo**: inicia conversaciones para verificar el bienestar y detecta apatía o tristeza que pasan desapercibidas en comunicaciones tradicionales.

### Demanda real identificada

**Sí.**

- **Validación con usuario real**: utilizado diariamente por una usuaria piloto (Marta, 83 años), demostrando adopción en entorno real.
- **Eventos críticos detectados por el algoritmo**: durante la operación piloto, el clasificador DISTRESS_LEVEL ya identificó y escaló a la familia eventos reales —incluyendo expresiones de desorientación, angustia emocional sostenida y menciones de caídas— que pasaban desapercibidos en llamadas telefónicas breves. Esto constituye tracción de uso medible más allá del volumen de conversaciones.
- **Tendencia demográfica**: crecimiento sostenido de adultos mayores que viven solos en Argentina y la región.
- **Interés de cuidadores**: demanda crítica de familiares que buscan reducir la incertidumbre sin dispositivos costosos.
- **Accesibilidad tecnológica**: adopción masiva de smartphones y Telegram en el segmento confirma la viabilidad del canal.

---

## 6. Escalabilidad

- **Arquitectura Basada en Software**: 100% digital sobre infraestructura serverless. Costo marginal por nuevo usuario cercano a cero.
- **Despliegue Global e Inmediato**: Telegram + APIs de LLM globales (Llama-3.3) → escalado de decenas a miles de usuarios sin barreras geográficas ni soporte presencial.
- **Economía de Escala en IA**: Groq permite procesar volúmenes masivos con latencia mínima manteniendo la calidad.
- **Potencial B2B2C**: integración con carteras de servicios de obras sociales, seguros y centros geriátricos.

---

## 7. Participación e Inversión Privada Recibida

- **Grado de Atracción de Capital**: etapa de bootstrapping (autofinanciado). Inversión privada aportada por los tres miembros del equipo fundador — Germán Villamarín, Ariel Brizi y Nicolás Gonzalez — destinada al MVP, validación con usuarios reales e infraestructura inicial.
- **Involucramiento Estratégico**: equipo senior en tecnología e ingeniería aporta expertise, horas y equipamiento como capital semilla operativo. El mismo equipo constituye la contraparte del 20% (USD 19.500) en el esquema de cofinanciamiento FONTAR.
- **Interés de Terceros**: conversaciones preliminares con instituciones de salud y especialistas en gerontología para validar el modelo de Sponsors que sostendrá la gratuidad.

**Síntesis (campo "grado de atracción de capital privado")**:
A la fecha, el proyecto se ha financiado mediante bootstrapping de los tres co-fundadores (Germán Villamarín, Ariel Brizi y Nicolás Gonzalez), logrando alcanzar un TRL 4 operativo. El equipo multidisciplinario senior aporta expertise en IA, infraestructura cloud y dirección tecnológica, y asume el cofinanciamiento del 20% del proyecto en especie. Se han iniciado conversaciones con instituciones del sector salud para la validación masiva, lo que constituye la base para futuras rondas de capital semilla.

---

## 8. Modelo de Negocios

### Fuentes de Monetización

- **B2B2C (Sponsors e Instituciones)**: instituciones de salud, obras sociales y seguros financian la operación a cambio de impacto social medible y visibilidad de marca.
- **Licencias de Monitoreo**: prestadores de cuidados domiciliarios y geriátricos pagan por el panel web y métricas de aislamiento.
- **Donaciones y Aportes**: fondos recurrentes de individuos o fundaciones.
- **Servicios de Valor Agregado**: suscripciones para familias con reportes analíticos avanzados o integraciones con dispositivos de salud.

### Estructura de Costos y Cofinanciamiento

El presupuesto total del proyecto es de **USD 97.500**, financiado bajo el esquema 80/20 previsto en el Art. 19° de las Bases: **USD 78.000 aportados por el FONTAR** (ANR) y **USD 19.500 aportados en especie por los tres miembros del equipo** — Germán Villamarín, Ariel Brizi y Nicolás Gonzalez — como contraparte obligatoria.

- **Honorarios del equipo fundador (≈46%)**: dedicación part-time de los tres miembros core (CTO, IA/LLM y Cloud/SRE) durante 15 meses para diseño, desarrollo, validación y dirección. Financiado por el ANR FONTAR.
- **Servicios técnicos externos (≈18%)**: auditoría de privacidad (Ley 25.326), asesoría gerontológica para validación con usuarios, UX/UI para el panel familiar, asesoría legal para sponsors e IP. Financiado por el ANR FONTAR.
- **APIs, cloud y desarrollo asistido por IA (≈15%)**: Groq (STT + LLM), ElevenLabs (TTS), hosting serverless, observabilidad y licencias de herramientas de desarrollo asistido por IA (Claude Code) que actúan como multiplicador de productividad y eliminan la necesidad de contratar un equipo de desarrollo dedicado. Financiado por el ANR FONTAR.
- **Validación con familias piloto (≈10%)**: reclutamiento, compensación (4 meses por familia) e instrumentación de la cohorte de 10 familias. Financiado por el ANR FONTAR.
- **Seguridad y comunicación institucional (≈10%)**: pen-testing, materiales de captación de sponsors, participación en eventos del sector salud y bienes de consumo de laboratorio. Financiado por el ANR FONTAR.
- **Contraparte del equipo (20% = USD 19.500)**: aportada en especie por Germán Villamarín, Ariel Brizi y Nicolás Gonzalez, en forma de horas adicionales de trabajo e infraestructura de desarrollo existente (equipamiento, entorno piloto activo, licencias previas).

---

## 9. Proyección de Rentabilidad y Sostenibilidad

- **Plazo al Equilibrio**: 18 meses después de finalizada la ejecución del proyecto financiado por FONTAR.
- **Lógica de Rentabilidad**: costos marginales decrecientes — software sobre canales existentes, costo de servir a miles de usuarios no escala linealmente con el costo de desarrollo.
- **Métricas de Valor**: ahorro de costos al sistema de salud por reducción de internaciones evitables; principal argumento de venta B2B.

### Sostenibilidad Financiera (B2B2C)

- Sponsoreo institucional (seguros, bancos, farmacéuticas).
- Licenciamiento a prestadores domiciliarios.
- Donaciones recurrentes que mantienen el acceso gratuito.

### Sostenibilidad Tecnológica

- Eficiencia en inferencia (Groq) para reducir dependencia de proveedores con costos dolarizados.
- Arquitectura serverless: costos crecen con el uso real.

### Sostenibilidad Social

- Gratuidad por diseño → retención de usuarios y datos para mejorar el algoritmo.
- Privacidad: capa local de ofuscación para cumplir con normativas de salud.

---

## 10. Mercado

### Segmentación

- **Usuarios Finales**: adultos mayores 65+ que viven solos, con smartphone y uso básico de Telegram.
- **Sponsors (B2B)**: medicina prepaga, obras sociales y aseguradoras interesadas en reducir costos operativos vía monitoreo preventivo.
- **Clientes Secundarios (B2C)**: familiares y cuidadores que buscan supervisión no invasiva.

### Canal de Comercialización

- **B2B2C**: alianzas con prestadores de salud para integrar aikiu como servicio de valor agregado.
- **Plataformas Digitales**: activación directa por Telegram, sin distribución física.
- **Red de Recomendación**: alianzas con gerontólogos y centros de jubilados.

### Validación y Captación de Valor

- **Generación de Valor**: conversación cotidiana → datos estructurados de bienestar.
- **Captación de Valor**: "Sponsorship" donde las instituciones financian la infraestructura a cambio de métricas agregadas y reducción de siniestralidad.
- **Barreras de Entrada**: mejora continua de DISTRESS_LEVEL basada en uso real.

### Riesgos y Mitigación (resumen mercado)

- **Dependencia tecnológica** (APIs de terceros): arquitectura modular → migración a open-source local.
- **Brecha digital**: interacción exclusiva por voz, sin GUI compleja.
- **Privacidad**: capa local de ofuscación y anonimización.

### Clientes objetivo y canal de comercialización (detalle)

- **Usuarios Finales (Beneficiarios)**: adultos mayores 65+ en áreas urbanas, con smartphone y familiarizados con mensajería.
- **Compradores/Sponsors (B2B)**: prepagas, obras sociales, seguros y prestadores domiciliarios.
- **Interesados Directos (B2C)**: hijos y nietos como red familiar.

**Estrategia B2B2C**: el prestador de salud integra aikiu como beneficio de valor agregado dentro de sus planes; despliegue masivo y gratuito para el usuario final.

**Plataformas Digitales**: activación en canales oficiales de mensajería y tiendas de aplicaciones; distribución nacional inmediata sin costos de instalación.

**Canales de Recomendación**: redes de gerontología, centros de jubilados y ONGs de tercera edad.

**Propuesta de Acceso**: modelo de "Fricción Cero" — el usuario solo envía una nota de voz; alta tasa de adopción en un segmento históricamente resistente.

**Captación de Valor**: licencias por volumen a Sponsors + acceso a panel de métricas agregadas, manteniendo gratuidad para usuario y familia.

---

## 11. Plan de Validación Técnica y Comercial

### Generación, captación y sostenibilidad del valor

- **Generación**: la interacción por voz se convierte en activos de salud preventiva. Detección temprana de deterioro cognitivo, apatía y soledad que los sistemas reactivos ignoran.
- **Captación**: Sponsorship B2B2C — instituciones financian, obtienen panel de métricas agregadas, optimizan recursos y reducen siniestralidad. Familias acceden gratis.
- **Sostenibilidad**:
  - *Efecto Red y Datos*: DISTRESS_LEVEL gana precisión con uso → barrera de entrada.
  - *Eficiencia Operativa*: serverless permite escalar con incremento mínimo en costos fijos.
  - *Fidelización Familiar*: alertas integran a la red familiar → ecosistema de confianza.

### Hitos de validación

- **Técnica**: 111 tests automatizados como línea de base, con meta de 250 al cierre de la Etapa 2 para garantizar estabilidad en despliegue masivo con latencia p95 < 3 s. Prototipo operativo con STT, LLM y TTS integrados; chequeos de inactividad, análisis nocturno y pre-routing determinístico corriendo en producción piloto.
- **Comercial**: validación en entorno real con usuario piloto y red familiar supervisora; eventos críticos reales escalados con éxito (desorientación, angustia, caídas). Aceptación de la interfaz de voz, utilidad de las alertas y configuración del perfil por parte de los familiares.
- **Institucional (entorno relevante, requisito TRL 6)**: firma de un convenio de cooperación técnica con un Centro de Jubilados o institución gerontológica en CABA, que aporte cohorte de usuarios y avale el protocolo de validación. Este convenio reemplaza la validación informal por un marco institucional verificable.

---

## 12. Riesgos principales y mitigación

- **Dependencia Tecnológica (Proveedores de IA)** — Groq, Llama, ElevenLabs.
  **Mitigación**: arquitectura modular desacoplada; hot-swap de proveedores; migración prevista a open-source local (Llama-3.1, Phi-3) en servidores propios si la escala lo justifica.
- **Baja Adopción por Brecha Digital**.
  **Mitigación**: estrategia de Fricción Cero — solo notas de voz en Telegram, sin menús ni instalaciones.
- **Cambios Regulatorios y Privacidad** — Ley 25.326.
  **Mitigación**: Privacy-by-Design; ofuscación local antes del envío a la nube; los LLM no pueden vincular conversación con identidad real.
- **Falsos Positivos en Alertas** — fatiga de alertas.
  **Mitigación**: tuning continuo de DISTRESS_LEVEL con la usuaria piloto; confirmación de "segundo paso" antes de escalar alertas críticas.
- **Sostenibilidad Financiera en el Escalado** — aumento de costos de inferencia.
  **Mitigación**: Sponsors Institucionales (B2B) absorben costo operativo como inversión en prevención.

---

## 13. Sostenibilidad (integral)

### Financiera

- **Sponsors (B2B)**: prepagas, seguros y bancos financian la infraestructura a cambio de impacto social y reducción de siniestralidad.
- **Licenciamiento B2B**: cobro por panel analítico a empresas de cuidados domiciliarios.
- **Costos**: arquitectura serverless → costos escalan con uso real.

### Tecnológica

- **Independencia de Proveedores**: módulos intercambiables STT/LLM/TTS por opciones open-source locales.
- **Mejora Continua**: DISTRESS_LEVEL se nutre del uso diario → barrera tecnológica que sostiene el valor.

### Social

- **Fricción Cero**: opera sobre Telegram → retención sin recapacitación.
- **Privacidad por Diseño**: ofuscación local cumple normativas de salud.
- **Comunidad**: la red familiar transforma el sistema en hábito de cuidado preventivo.

---

## 14. Calidad Técnica y Organizativa del Proyecto

### Perfil del Líder (máx. 700 caracteres)

Germán Villamarin (UBA, Lic. en Análisis de Sistemas; Posgrado en Project Management, Universidad de Belgrano) es CTO con +25 años en tecnología y operaciones del sector financiero latinoamericano. Actualmente CITO en PUENTE, una de las ALyC líderes de Argentina (regulada por CNV y BYMA). Antes, VP IT & Operations en Scotiabank Uruguay (290 personas, transformación digital end-to-end) y Technical Director en Santander Argentina (+100 profesionales, BCRA, programa de fidelización Superclub+ con 4M de clientes). Experto en cloud-native, microservicios, ciberseguridad y aplicación de IA al negocio.

### Integrantes y experiencia del equipo

CV completos (<2 páginas cada uno) y perfiles de LinkedIn en `Equipo/`.

**Germán Villamarin — Líder del Proyecto · CTO**
- *Formación*: Licenciado en Análisis de Sistemas (UBA, 1990-2000); Posgrado en Project Management (Universidad de Belgrano, 2007); Técnico Electricista (Escuela Técnica Otto Krause, 1983-1988).
- *Trayectoria (+25 años en finanzas Latam)*: CITO en PUENTE (ALyC, desde 2024, CNV/BYMA); VP IT & Operations en Scotiabank Uruguay (2023-2024, 290 personas, cloud-native y microservicios); Technical Director en Santander Argentina (2019-2023, +100 personas, BCRA, plataforma Superclub+ con 4M clientes); Consultor Independiente en AIKIU (2013-2019); Gerente Regional Latam en Marketing Consultants (2006-2012); Co-fundador de enfoke (2000-2006); Gerente de Nuevos Proyectos en Banco Hipotecario (1996-2000).
- *Especialidad*: arquitecturas cloud-native, ciberseguridad financiera, modernización legacy → microservicios, IA aplicada.

**Ariel Brizi — IA / LLM**
- *Formación*: Ingeniero en Sistemas de Información (UTN); certificación Scrum Grand Master.
- *Trayectoria*: Head Regional de Innovación Tecnológica en PUENTE Argentina (desde 2025); Tech Director y Tech Manager en Globant (Práctica Medios de Pago, 2019-2024); Project Leader en Mercadolibre/MercadoPago (gateway de pagos, 2017-2019); Team Leader y J2EE Sr en Banco Itaú Argentina (2010-2017); Analista Programador J2EE SSr en everis - Movistar (2008-2010).
- *Especialidad*: LLMs y RAGs aplicados al desarrollo, arquitectura de microservicios, plataformas de pago de alto volumen, Java/Go, Kafka, Redis, clean/hexagonal architecture.

**Nicolás Gonzalez — Cloud / SRE / FinOps**
- *Formación*: Licenciado en Análisis de Sistemas (UBA, 1990-1997); Posgrado en Banking (Universidad Torcuato Di Tella, 2005); Programa de Formación de Capacidades Molinos (IAE Business School, 2009-2010); cursó Ingeniería Industrial en el ITBA (1987-1990).
- *Trayectoria (+30 años en infraestructura)*: Sr VP Cloud Ops en Siigo Colombia (2023-2026, Azure, AKS, observabilidad); Director de Infraestructura y Corporate Apps en Clip México (2022-2023, AWS ECS, Lambda); Architecture Technical Director en Santander Argentina (2019-2022, SecDevOps, OpenShift, ALM); Gerente de Tecnología y Operaciones en Universidad Austral / IAE Business School (2016-2019); Gerente de Servicios Informáticos en Newsan (2013-2016, ISO 27001, 4 datacenters); Jefe de Tecnología en Molinos Río de la Plata (2007-2013, SAP); Jefe de Tecnología en Banco Hipotecario (1999-2007).
- *Especialidad*: CloudOps, SRE, FinOps, DevOps/SecDevOps, observabilidad (Grafana, Datadog, Site24x7), seguridad ISO 27001.

### Dedicación al proyecto

El equipo core está conformado por los tres miembros descriptos arriba, con la siguiente dedicación part-time durante los 15 meses del proyecto:

- **Germán Villamarin (CTO / Dirección técnica y de producto, arquitectura crítica)**: 20 h/semana.
- **Ariel Brizi (IA/LLM — algoritmo DISTRESS_LEVEL, RAG, integración de APIs de inferencia)**: 20 h/semana.
- **Nicolás Gonzalez (Cloud/SRE — observabilidad, FinOps, ciberseguridad)**: 20 h/semana.

No se contempla la contratación de un equipo de desarrollo dedicado. La capacidad de ejecución se apalanca en el uso intensivo de **herramientas de desarrollo asistido por IA (Claude Code)** que multiplican la productividad de cada miembro core, evitando estructura fija de ingeniería y manteniendo la coherencia conceptual del producto en pocas manos. El consumo de tokens y suscripciones de estas herramientas está contemplado dentro del rubro de APIs y desarrollo del presupuesto (sección 16).

### Plan de Trabajo por Fases

El proyecto se divide en tres fases secuenciales:

- **Fase 1 (meses 1–3)**: diseño de arquitectura Privacy-by-Design y capas de ofuscación de datos para seguridad del usuario.
- **Fase 2 (meses 4–9)**: entrenamiento y fine-tuning del modelo de detección de angustia, y validación de métricas de bienestar con la cohorte piloto durante 4 meses sostenidos.
- **Fase 3 (meses 10–15)**: integración técnica B2B, pruebas de carga y escalado de la infraestructura para despliegue masivo.

### Justificación Técnica

- **Capacidad**: equipo con trayectoria senior en PUENTE, Scotiabank, Santander, Globant, Mercadolibre/MercadoPago, Banco Itaú, Clip, Siigo, Molinos Río de la Plata y Banco Hipotecario — sistemas financieros masivos y entornos regulados por BCRA, CNV y BYMA.
- **Base Científica**: combinación de expertos en IA aplicada (LLMs y RAGs), infraestructura cloud y FinOps, y dirección tecnológica en banca, que cubre todo el ciclo necesario para llevar el proyecto de TRL 4 a TRL 6.
- **Cohesión del equipo**: dos de los tres miembros (Germán y Ariel) trabajan actualmente juntos en PUENTE; Germán y Nicolás compartieron Santander Argentina entre 2019 y 2022. Existe un track record real de colaboración previa.
- **Apalancamiento por IA**: el uso de desarrollo asistido por modelos de IA (Claude Code) permite al equipo core ejecutar sin contratar ingeniería externa adicional, manteniendo bajo el costo total del proyecto y consistente la arquitectura.

---

## 15. Plan de Trabajo (Anexo I)

**Duración total**: 15 meses. **TRL objetivo al cierre**: 6.

### 15.1 Etapa 1 — Privacy-by-Design (meses 1 a 3)

**Actividades**: diseño de la capa local de ofuscación y anonimización; definición de la taxonomía de datos sensibles (PII y datos de salud bajo Ley 25.326); implementación del módulo de pre-procesamiento previo al envío a LLM; auditoría externa inicial.

**Entregables**: especificación técnica de privacidad; módulo `core/privacy.py` con cobertura de tests ≥85%; informe de auditoría externa de privacidad.

**Hito de validación**: conversaciones reales en entorno piloto muestran cero datos PII salientes hacia APIs externas.

**Dedicación**: Germán 20 h/sem; Ariel 20 h/sem; Nicolás 20 h/sem.

### 15.2 Etapa 2 — DISTRESS_LEVEL v2 y validación con 10 familias (meses 4 a 9)

**Actividades**: curado del dataset conversacional anonimizado; fine-tuning del clasificador DISTRESS_LEVEL 0–3; reducción de falsos positivos mediante confirmación de "segundo paso"; reclutamiento y validación con cohorte de 10 familias piloto; entrevistas semiestructuradas con familiares supervisores.

**Entregables**: modelo entrenado con métricas de precisión/recall por nivel; reporte de validación con 10 familias; panel inicial de métricas de bienestar para uso interno; **convenio de cooperación técnica firmado con un Centro de Jubilados o institución gerontológica de CABA** que avale el protocolo de validación y aporte cohorte adicional de usuarios.

**Hito de validación**: F1 ≥0.80 en niveles 2 y 3 del clasificador; tasa de falsos positivos ≤10%; las 10 familias mantienen uso sostenido durante al menos 4 meses; convenio institucional firmado y operativo.

**Dedicación**: Germán 20 h/sem; Ariel 20 h/sem; Nicolás 20 h/sem.

### 15.3 Etapa 3 — Escalado e Integración B2B (meses 10 a 15)

**Actividades**: pruebas de carga sobre infraestructura serverless; integración con webhooks de prestadores institucionales; migración opcional a modelo open-source local (Llama-3.1 o Phi-3) como fallback; desarrollo del panel web para cuidadores; documentación de la API; captación comercial de al menos un sponsor institucional.

**Entregables**: suite de pruebas de carga para 1.000 usuarios concurrentes; API documentada en OpenAPI; panel web v1 (vista cuidador); carta de intención firmada por al menos una institución de salud.

**Hito de validación**: el sistema sostiene 1.000 usuarios concurrentes con latencia p95 menor a 3 segundos.

**Dedicación**: Germán 20 h/sem; Ariel 20 h/sem; Nicolás 20 h/sem.

### 15.4 Cronograma resumen

La Etapa 1 ocupa los meses 1 a 3, la Etapa 2 los meses 4 a 9 (con superposición de actividades de reclutamiento de familias desde el mes 4) y la Etapa 3 los meses 10 a 15. La validación con la usuaria piloto actual (Marta) se mantiene de forma continua durante los 15 meses, como banco de pruebas estable para todas las iteraciones. El plazo extendido a 15 meses permite ampliar la compensación de las familias piloto a 4 meses de validación sostenida (vs. 3 meses originales) y fortalecer las actividades comerciales e institucionales de la Etapa 3.

### 15.5 Indicadores de Seguimiento y Monitoreo

**Indicadores de productos intermedios (por etapa):**

- **E1 — Mes 3**: módulo `core/privacy.py` implementado y auditado. Indicadores: cobertura de tests automatizados ≥85% sobre el módulo; cero datos PII salientes verificados en muestra de 100 conversaciones reales; informe de auditoría externa emitido.
- **E2 — Mes 6**: clasificador DISTRESS_LEVEL v2 entrenado. Indicadores: F1 ≥0.80 en niveles 2 y 3; tasa de falsos positivos ≤10%; dataset curado con ≥500 conversaciones etiquetadas; convenio institucional con Centro de Jubilados o institución gerontológica firmado.
- **E2 — Mes 9**: validación con cohorte piloto completada. Indicadores: 10 familias con uso sostenido ≥4 meses; tasa de retención de usuarios ≥70%; reporte de validación con métricas de uso y satisfacción entregado; panel interno de métricas operativo.
- **E3 — Mes 12**: infraestructura de escalado validada. Indicadores: sistema sostiene 1.000 usuarios concurrentes con latencia p95 <3 segundos; API documentada en OpenAPI 3.0 publicada; panel web v1 para cuidadores funcional.
- **E3 — Mes 15**: integración comercial e institucional alcanzada. Indicadores: al menos 1 carta de intención firmada por institución de salud; asesoría legal de IP completada.

**Indicadores de producto final (cierre del proyecto — TRL 6):**

- Tests automatizados: 111 → **250** (pytest, cobertura integral del sistema).
- Usuarios activos diarios: 1 → **≥10** (cohorte piloto validada).
- Familias supervisoras activas: 1 → **10** (cohorte E2).
- Latencia p95 de respuesta de voz: **<3 segundos** con 1.000 usuarios concurrentes.
- Clasificador DISTRESS_LEVEL: **F1 ≥0.80** en niveles críticos (2 y 3).
- Datos PII salientes hacia APIs externas: **0** (verificado por auditoría).
- Convenios institucionales: **≥1** firmado y operativo.
- Cartas de intención B2B: **≥1** de institución de salud.
- Aprendizajes nuevos incorporados por el análisis nocturno: **≥3 por semana** por usuario activo en promedio.

**Indicadores continuos (meses 1–15):**

- Informes técnicos de avance presentados vía TAD: **≥3** durante la ejecución.
- Rendición de gastos: **≥70%** del desembolso anterior antes de cada nuevo desembolso (Art. 43° de las Bases).
- Disponibilidad del sistema piloto: **≥99%** uptime mensual medido por herramienta de observabilidad.

---

## 16. Presupuesto Detallado (USD 97.500)

El presupuesto se distribuye en cinco rubros principales. La extensión del plazo a 15 meses (vs. 12 meses originales) incrementa el costo total de USD 80.000 a USD 97.500, con el delta concentrado principalmente en honorarios del equipo (3 meses adicionales × 3 personas × USD 1.000/mes = USD 9.000) y en el mayor alcance de los rubros de APIs, validación de familias y servicios técnicos externos en consonancia con el plazo extendido.

**Honorarios del equipo fundador — 45.000 USD (46,2%)**. Dedicación part-time de los tres miembros core durante 15 meses, financiando esfuerzo nuevo dedicado al proyecto que hoy no está remunerado (el equipo se encuentra en etapa de bootstrapping). Distribución: Germán Villamarin 15.000 USD (1.000/mes × 15), Ariel Brizi 15.000 USD (1.000/mes × 15) y Nicolás Gonzalez 15.000 USD (1.000/mes × 15). Estos montos respetan la cap de honorarios habitual de los aportes ANR FONTAR.

**Servicios técnicos externos — 18.000 USD (18,5%)**. Contratación puntual de capacidades que el equipo core no posee de manera directa: auditoría externa de privacidad y cumplimiento de Ley 25.326 (4.000 USD); asesoría gerontológica para diseño del protocolo de validación con familias (3.000 USD, extendida a 6 meses por el mayor plazo); diseño UX/UI y desarrollo del panel web familiar por contractor externo (4.000 USD, mayor alcance); pen-testing de los bots de Telegram (3.000 USD, auditoría más completa); asesoría legal para contratos con sponsors y política de propiedad intelectual (2.000 USD); investigación con usuarios y entrevistas semiestructuradas (2.000 USD, mayor volumen por plazo extendido). Total ≤ 20% del ANR, conforme Art. 21°c de las Bases.

**APIs, cloud y desarrollo asistido por IA — 15.000 USD (15,4%)**. Groq para STT (Whisper-large-v3) y LLM (Llama-3.3-70b) (5.000 USD, 15 meses); ElevenLabs para TTS premium en español (2.500 USD, 15 meses); **licencias y consumo de Claude Code para desarrollo asistido por IA** (5.000 USD; aproximadamente 110 USD/mes por cada uno de los tres miembros del equipo durante 15 meses — este rubro reemplaza la contratación de un equipo de ingeniería dedicado); hosting serverless y CDN (1.500 USD, 15 meses); observabilidad y monitoring (1.000 USD, 15 meses).

**Validación con familias piloto — 10.000 USD (10,3%)**. Reclutamiento de las 10 familias piloto (1.000 USD); compensación por participación durante 4 meses de validación sostenida (4.000 USD — 1 mes adicional respecto al plan original, habilitado por el plazo extendido); instrumentación, tooling y herramientas de medición (2.500 USD); cohortes de entrevistas semiestructuradas y procesamiento cualitativo (2.500 USD, mayor volumen).

**Seguridad institucional y comunicación — 9.500 USD (9,7%)**. Materiales de captación de sponsors y desarrollo del pitch institucional (2.500 USD); participación en eventos del sector salud y redes de gerontología (3.000 USD — más eventos en 15 meses); herramientas de seguridad complementarias y revisión periódica de vulnerabilidades (1.500 USD); bienes de consumo de laboratorio: smartphones de prueba, conectividad y dispositivos para escenarios de validación (2.500 USD).

**Esquema de cofinanciamiento (Art. 19° y 44° de las Bases)**:
- **ANR FONTAR (80%)**: USD 78.000 — aportados por la Agencia I+D+i.
- **Contraparte del equipo beneficiario (20%)**: USD 19.500 — aportados en especie por los tres miembros del equipo: **Germán Villamarín**, **Ariel Brizi** y **Nicolás Gonzalez**. El aporte en especie se compone de: (a) horas de trabajo adicionales sobre las contempladas en el rubro de honorarios financiado por el ANR, equivalentes en tiempo de preparación, coordinación y gestión del proyecto; y (b) infraestructura de desarrollo existente (equipamiento, licencias previas, entorno de producción piloto activo). Los tres co-fundadores asumen solidariamente este compromiso de contraparte como inversión en el desarrollo del proyecto.

> **TODO**: alinear estos rubros con la nomenclatura oficial FONTAR (Anexo I — Tablas Plan de Trabajo) y volcar el detalle al Excel del anexo.

---

## 17. Resultados e Impacto Esperados

- **Tecnológico**: validación de una infraestructura de cuidado basada en IA con costos marginales cercanos a cero, módulo Privacy-by-Design auditado y clasificador DISTRESS_LEVEL con F1 ≥0.80 en niveles críticos. Cierre del proyecto en TRL 6.
- **Social**: reducción del estrés del cuidador, mejora de autonomía y compañía diaria del adulto mayor. 10 familias piloto con uso sostenido ≥4 meses.
- **Económico**: modelo de sostenibilidad B2B2C validado mediante al menos una carta de intención de institución de salud; eliminación de la barrera económica para la familia.
- **Indicadores cuantitativos a alcanzar**:
  - Usuarios activos diarios: 10 → 100.
  - Familias supervisoras activas: 1 → 10 (cohorte piloto E2).
  - Tests automatizados: 111 → 250.
  - Latencia p95 de respuesta de voz: <3s con 1k usuarios concurrentes.
  - Aprendizajes nuevos incorporados por el análisis nocturno: ≥3/semana en promedio por usuario activo.
  - Cero datos PII salientes hacia APIs externas (verificado por auditoría).

---

## 18. Stack Tecnológico y Documentación de Respaldo

- **Lenguaje**: Python 3.14.
- **STT**: Groq Whisper-large-v3.
- **LLM**: Llama-3.3-70b-versatile (Groq), con fallback previsto a Llama-3.1 / Phi-3 local.
- **TTS**: edge-tts + ffmpeg (es-AR-ElenaNeural, OGG OPUS); upgrade previsto a ElevenLabs en E3.
- **Canal**: `python-telegram-bot 21.6` — dos bots: asistente personal del adulto mayor + bot familiar compartido.
- **Scheduler**: APScheduler 3.10 — saludo matutino, recordatorios, chequeos de inactividad y análisis nocturno.
- **Módulos propietarios**:
  - `core/distress.py` — parsing del nivel de angustia y cooldowns.
  - `core/alerts.py` — envío de alertas a la red familiar.
  - `core/tools.py` — pre-routing determinístico para clima, dólar y noticias.
  - `aikiu.analisis_nocturno` — extracción de aprendizajes y ajustes diarios.
- **Testing**: `pytest 9.0` — 111 tests automatizados (unitarios e integración); pre-commit hook que los ejecuta antes de cada commit.
- **Persistencia**: archivos locales (`perfil.md` editable por la familia, `subscribers.json`, `familiares.json`) + logs diarios estructurados en `logs/YYYY-MM-DD.md`.
- **Infraestructura**: ejecución sobre Mac del fundador en fase piloto; arquitectura serverless prevista para escalado.
- **Seguridad**: secretos en `.env` (fuera del repo); bots restringidos a `chat_id` autorizados.
- **Repositorio**: GitHub (acceso restringido a evaluadores).

---

## 19. Evidencias de Desarrollo Tecnológico

Esta sección reúne los archivos que se entregarán como anexos de evidencia. Mantener actualizado el inventario a medida que se generan.

### 19.1 Inventario de evidencias

**Evidencias ya existentes** (incluidas en el repositorio):

- *Código fuente del core*: repositorio Python con `aikiu.py` y módulos `core/` (acceso restringido para evaluadores).
- *Roadmap*: plan de evolución de TRL 4 a TRL 6 en `ROADMAP.md`.
- *Pitch deck*: presentación para inversores en `investors/aikiu-pitch.pptx`.
- *Guion de demo*: script paso a paso de la demo en vivo en `investors/guion-demo.md`.
- *CVs y perfiles de LinkedIn del equipo*: carpeta `Equipo/` dentro de este directorio FONTAR.

**Evidencias a generar antes de la presentación**:

- *Reporte de tests*: captura del resultado de `pytest` con los 111 tests automatizados pasando, archivo `evidencias/01-tests-output.png`.
- *Log anonimizado*: extracto de `aikiu.log` con interacciones reales con datos sensibles enmascarados, archivo `evidencias/02-log-anonimizado.txt`.
- *Video demo*: grabación end-to-end de la demo (voz del usuario → LLM → alerta a familiar), archivo `evidencias/03-demo.mp4`.
- *Captura Telegram lado usuaria*: pantalla de Marta conversando con Clara, archivo `evidencias/04-telegram-marta.png`.
- *Captura Telegram lado familiar*: alerta de DISTRESS_LEVEL recibida en el bot familiar, archivo `evidencias/05-telegram-familiar.png`.
- *Comandos del bot familiar*: capturas de los comandos `/perfil`, `/editar` y `/mensaje` que demuestran la supervisión y configuración familiar, archivo `evidencias/06-bot-familiar-comandos.png`.
- *Alerta de inactividad*: captura de la alerta automática enviada a la familia tras N horas sin comunicación del adulto mayor, archivo `evidencias/07-alerta-inactividad.png`.
- *Análisis nocturno*: diff del archivo `perfil.md` antes y después de la ejecución del análisis nocturno, mostrando aprendizajes nuevos y ajustes sugeridos, archivo `evidencias/08-analisis-nocturno-diff.md`.
- *Diagrama de arquitectura*: bloques del sistema con STT, LLM, TTS, scheduler, capa de privacy y bot familiar, archivo `evidencias/09-arquitectura.png`.
- *Documento técnico del algoritmo DISTRESS_LEVEL*: explicación de la escala 0–3, prompt utilizado y ejemplos de clasificación, archivo `evidencias/10-distress-level.pdf`.
- *Informe de validación piloto*: bitácora de uso de la usuaria piloto durante el período de validación, archivo `evidencias/11-validacion-piloto.pdf`.

### 19.2 Organización propuesta

Crear la carpeta `evidencias/` dentro del directorio de FONTAR con la siguiente estructura:

```
investors/Fondos/2026.05 - Fontar/
├── formulario.md
├── 25-12_byc_convocatoria_startup_2025_trl_3-4.pdf
├── 25-12_anexos_startup_trl_3-4 (extract.me)/
└── evidencias/
    ├── 01-tests-output.png
    ├── 02-log-anonimizado.txt
    ├── 03-demo.mp4
    ├── 04-telegram-marta.png
    ├── 05-telegram-familiar.png
    ├── 06-bot-familiar-comandos.png
    ├── 07-alerta-inactividad.png
    ├── 08-analisis-nocturno-diff.md
    ├── 09-arquitectura.png
    ├── 10-distress-level.pdf
    └── 11-validacion-piloto.pdf
```

### 19.3 Criterios de inclusión

- **Anonimización**: todas las capturas y logs deben tener nombres, números de teléfono, direcciones y datos sensibles enmascarados antes de adjuntarse.
- **Trazabilidad**: cada evidencia debe llevar fecha (`YYYY-MM-DD`) y, cuando aplique, hash SHA-256 para integridad.
- **Reproducibilidad**: los outputs técnicos (tests, métricas) deben acompañarse del comando exacto que los generó.

---

## TODOs / pendientes para cerrar

- [ ] Definir "Institución Beneficiaria".
- [ ] Validar conteo final del perfil del líder ≤700 caracteres en el formato definitivo del formulario.
- [ ] Revisar contra "04. Anexo IV - Matriz Evaluación Start Up 3-4.pdf" para validar criterios de puntaje.
- [x] Volcar el plan de trabajo detallado en "01. Anexos - Tablas Plan de Trabajo.xlsx" — **completado** (15 meses, USD 97.500, 3 desembolsos).
- [x] Alinear los rubros del presupuesto con la nomenclatura oficial FONTAR — **completado** en el xlsx.
- [ ] Crear carpeta `evidencias/` y generar los ítems pendientes (ver §19.1).
- [ ] Decidir si se solicita protección de IP (hoy: No) y registrar política.
