# Estrategia de Fortalecimiento — Proyecto aikiu (FONTAR)

Este documento detalla las modificaciones estructurales y técnicas para elevar la propuesta al estándar de **TRL 6**, asegurando coherencia entre el desarrollo actual y el formulario de subsidio.

---

## 1. Reencuadre y Sincronización Técnica
Se debe capitalizar la arquitectura actual para demostrar que el proyecto es un sistema de ingeniería robusto y no solo una interfaz sobre un chat.

* **Pre-routing Determinístico (Secciones 4 y 5)**:
    * **Propuesta**: Resaltar que `aikiu` no depende de la generación creativa de un LLM para datos factuales.
    * **Impacto**: El uso de motores de consulta directa a fuentes oficiales (`wttr.in`, `dolarapi.com`, `RSS La Nación`) garantiza información veraz y mitiga riesgos de alucinaciones en adultos mayores.
* **Análisis Nocturno Autónomo (Sección 4)**:
    * **Propuesta**: Incluir esta capacidad como una mejora crítica en la eficiencia operativa y de costos.
    * **Impacto**: Permite la extracción de aprendizajes y ajustes de comportamiento sin intervención técnica constante.
* **Bot Familiar Compartido (Sección 2)**:
    * **Propuesta**: Posicionar el bot de supervisión como un centro de control multicuidador.
    * **Impacto**: Diferencia a `aikiu` de asistentes genéricos al colocar a la red familiar como supervisora central del cuidado.

---

## 2. Robustecimiento de la Validación y Tracción
Utilizar la casuística real para demostrar que el algoritmo ya resuelve problemas críticos en el entorno del adulto mayor.

* **Evidencia de Uso Real (Secciones 5 y 11)**:
    * **Acción**: Citar aprendizajes registrados (desorientación, angustia emocional, caídas) como validación del algoritmo `DISTRESS_LEVEL`.
    * **Impacto**: Demuestra "Tracción de Uso" mediante la resolución de eventos críticos no médicos en un entorno piloto.
* **Validación Institucional (Sección 15)**:
    * **Propuesta**: Reemplazar la validación informal por un convenio de cooperación técnica con un Centro de Jubilados o Institución Gerontológica en CABA.
    * **Impacto**: Proyecta una validación sólida en un "entorno relevante", requisito clave para alcanzar el `TRL 6`.

---

## 3. Seguridad, Privacidad y Normativa
Elevar la jerarquía técnica de la protección de datos para alinearse con los estándares de salud.

* **Capa de Ofuscación Local (Secciones 12 y 13)**:
    * **Propuesta**: Implementación de una capa de sanitización (*Privacy-by-Design*) que anonimiza datos antes del procesamiento en la nube.
    * **Impacto**: Asegura cumplimiento estricto de la Ley 25.326 y permite operación en entornos locales sin dependencia absoluta de la red.
* **Soberanía Tecnológica**:
    * **Acción**: Declarar la capacidad de realizar un *hot-swap* hacia modelos *Open Source* (`Llama-3.1`, `Phi-3`) ante riesgos de costos o privacidad.

---

## 4. Indicadores y Calidad de Software
Sustituir proyecciones teóricas por métricas de ingeniería verificables.

* **Línea de Base de Calidad (Sección 17)**:
    * **Dato**: El proyecto ya cuenta con **111 tests unitarios automatizados**.
    * **Meta**: Alcanzar los 250 tests al finalizar la Etapa 2 para garantizar estabilidad en el despliegue masivo con latencia p95 < 3s