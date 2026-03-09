from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Painel ScriptLattes",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# ESTILO
# ============================================================
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
    .stMetric {
        border: 1px solid rgba(49, 51, 63, 0.15);
        border-radius: 16px;
        padding: 0.8rem 1rem;
        background: rgba(255, 255, 255, 0.02);
    }
    .small-note {
        font-size: 0.92rem;
        color: #6b7280;
    }
    .code-box {
        background: #0b1020;
        color: #eef2ff;
        padding: 0.85rem 1rem;
        border-radius: 12px;
        font-family: monospace;
        overflow-x: auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CONSTANTES
# ============================================================
DEFAULT_REPO_DIR = Path("scriptLattes-main")
RUNS_DIR = Path("streamlit_runs")

PRODUCAO_LABELS = {
    "artigos_periodicos": "Artigos em periódicos",
    "livros_publicados": "Livros publicados",
    "capitulos_livros": "Capítulos de livros",
    "trabalhos_completos_congressos": "Trabalhos completos em congressos",
    "resumos_expandidos": "Resumos expandidos",
    "resumos_congressos": "Resumos em congressos",
    "artigos_aceitos": "Artigos aceitos",
    "apresentacoes_trabalhos": "Apresentações de trabalhos",
    "textos_jornais": "Textos em jornais",
    "outros": "Outras produções bibliográficas",
}

ORIENTACAO_LABELS = {
    "pos_doutorado": "Pós-doutorado",
    "doutorado": "Doutorado",
    "mestrado": "Mestrado",
    "especializacao": "Especialização",
    "tcc": "TCC",
    "iniciacao_cientifica": "Iniciação científica",
    "outro_tipo": "Outro tipo",
}


# ============================================================
# FUNÇÕES UTILITÁRIAS
# ============================================================
def slugify(texto: str) -> str:
    texto = re.sub(r"[^\w\s-]", "", texto.strip(), flags=re.UNICODE)
    texto = re.sub(r"[-\s]+", "-", texto)
    return texto.lower() or "grupo"


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, list):
        partes = [str(v).strip() for v in valor if str(v).strip()]
        return " | ".join(partes)
    return str(valor).strip()


def bytes_to_zip(folder_path: Path) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(folder_path))
    mem.seek(0)
    return mem.getvalue()


def save_uploaded_file(uploaded_file, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(uploaded_file.getbuffer())
    return destination


def parse_manual_ids(texto: str) -> list[str]:
    linhas = []
    for raw in texto.splitlines():
        linha = raw.strip().strip(",")
        if not linha:
            continue
        linhas.append(linha)
    return linhas


def build_list_file(uploaded_list, manual_ids_text: str, run_input_dir: Path) -> Path:
    caminhos = []

    if uploaded_list is not None:
        uploaded_path = save_uploaded_file(uploaded_list, run_input_dir / uploaded_list.name)
        caminhos.append(uploaded_path)

    manual_lines = parse_manual_ids(manual_ids_text)
    if manual_lines:
        manual_path = run_input_dir / "ids_digitados.list"
        manual_path.write_text("\n".join(manual_lines), encoding="utf-8")
        caminhos.append(manual_path)

    if not caminhos:
        raise ValueError("Envie um arquivo .list/.txt ou digite pelo menos um ID Lattes.")

    if len(caminhos) == 1:
        return caminhos[0]

    merged_path = run_input_dir / "entrada_consolidada.list"
    conteudo = []
    for path in caminhos:
        conteudo.append(path.read_text(encoding="utf-8", errors="ignore").strip())
    merged_path.write_text("\n".join([c for c in conteudo if c]), encoding="utf-8")
    return merged_path


def build_terms_file(uploaded_terms, run_input_dir: Path) -> Path | None:
    if uploaded_terms is None:
        return None
    return save_uploaded_file(uploaded_terms, run_input_dir / uploaded_terms.name)


def build_config_text(
    nome_grupo: str,
    arquivo_entrada: Path,
    diretorio_saida: Path,
    ano_inicio: int,
    ano_fim: int,
    itens_por_pagina: int,
    idioma: str,
    incluir_grafo: bool,
    mostrar_todos_nos: bool,
    considerar_rotulos: bool,
    identificar_termos: bool,
    arquivo_termos: Path | None,
) -> str:
    sim_nao = lambda v: "sim" if v else "nao"

    linhas = [
        "# ----------------------------------------------------------------------------- #",
        "# Arquivo gerado automaticamente pelo app Streamlit                            #",
        "# ----------------------------------------------------------------------------- #",
        f"global-nome_do_grupo                      = {nome_grupo}",
        f"global-arquivo_de_entrada                 = {arquivo_entrada.as_posix()}",
        f"global-diretorio_de_saida                 = {diretorio_saida.as_posix()}",
        "global-email_do_admin                     = admin@email.com",
        f"global-idioma                             = {idioma}",
        f"global-itens_desde_o_ano                  = {ano_inicio}",
        f"global-itens_ate_o_ano                    = {ano_fim}",
        f"global-itens_por_pagina                   = {itens_por_pagina}",
        f"global-identificar_producoes_por_termos   = {sim_nao(identificar_termos)}",
        f"global-arquivo_de_termos_de_busca         = {(arquivo_termos.as_posix() if arquivo_termos else '')}",
        "",
        "# ----------------------------------------------------------------------------- #",
        "# RELATÓRIOS DE PRODUÇÃO EM C, T & A                                            #",
        "# ----------------------------------------------------------------------------- #",
        "relatorio-incluir_artigo_em_periodico                  = sim",
        "relatorio-incluir_livro_publicado                      = sim",
        "relatorio-incluir_capitulo_de_livro_publicado          = sim",
        "relatorio-incluir_texto_em_jornal_de_noticia           = sim",
        "relatorio-incluir_trabalho_completo_em_congresso       = sim",
        "relatorio-incluir_resumo_expandido_em_congresso        = sim",
        "relatorio-incluir_resumo_em_congresso                  = sim",
        "relatorio-incluir_artigo_aceito_para_publicacao        = sim",
        "relatorio-incluir_apresentacao_de_trabalho             = sim",
        "relatorio-incluir_outro_tipo_de_producao_bibliografica = sim",
        "",
        "relatorio-incluir_software_com_registro                = sim",
        "relatorio-incluir_software_sem_registro                = sim",
        "relatorio-incluir_produto_tecnologico                  = sim",
        "relatorio-incluir_processo_ou_tecnica                  = sim",
        "relatorio-incluir_trabalho_tecnico                     = sim",
        "relatorio-incluir_outro_tipo_de_producao_tecnica       = sim",
        "relatorio-incluir_entrevista_mesas_e_comentarios       = sim",
        "",
        "relatorio-incluir_producao_artistica                   = sim",
        "",
        "# ----------------------------------------------------------------------------- #",
        "# RELATÓRIOS DE ORIENTAÇÕES                                                     #",
        "# ----------------------------------------------------------------------------- #",
        "relatorio-mostrar_orientacoes                                          = sim",
        "relatorio-incluir_orientacao_em_andamento_pos_doutorado                = sim",
        "relatorio-incluir_orientacao_em_andamento_doutorado                    = sim",
        "relatorio-incluir_orientacao_em_andamento_mestrado                     = sim",
        "relatorio-incluir_orientacao_em_andamento_monografia_de_especializacao = sim",
        "relatorio-incluir_orientacao_em_andamento_tcc                          = sim",
        "relatorio-incluir_orientacao_em_andamento_iniciacao_cientifica         = sim",
        "relatorio-incluir_orientacao_em_andamento_outro_tipo                   = sim",
        "",
        "relatorio-incluir_orientacao_concluida_pos_doutorado                   = sim",
        "relatorio-incluir_orientacao_concluida_doutorado                       = sim",
        "relatorio-incluir_orientacao_concluida_mestrado                        = sim",
        "relatorio-incluir_orientacao_concluida_monografia_de_especializacao    = sim",
        "relatorio-incluir_orientacao_concluida_tcc                             = sim",
        "relatorio-incluir_orientacao_concluida_iniciacao_cientifica            = sim",
        "relatorio-incluir_orientacao_concluida_outro_tipo                      = sim",
        "",
        "# ----------------------------------------------------------------------------- #",
        "# RELATÓRIOS ADICIONAIS                                                        #",
        "# ----------------------------------------------------------------------------- #",
        "relatorio-incluir_projeto                = sim",
        "relatorio-incluir_premio                 = sim",
        "relatorio-incluir_participacao_em_evento = sim",
        "relatorio-incluir_organizacao_de_evento  = sim",
        "",
        "# ----------------------------------------------------------------------------- #",
        "# GRAFO DE COLABORAÇÕES                                                        #",
        "# ----------------------------------------------------------------------------- #",
        f"grafo-mostrar_grafo_de_colaboracoes                         = {sim_nao(incluir_grafo)}",
        f"grafo-mostrar_todos_os_nos_do_grafo                         = {sim_nao(mostrar_todos_nos)}",
        f"grafo-considerar_rotulos_dos_membros_do_grupo               = {sim_nao(considerar_rotulos)}",
        "",
        "grafo-incluir_artigo_em_periodico                           = sim",
        "grafo-incluir_livro_publicado                               = sim",
        "grafo-incluir_capitulo_de_livro_publicado                   = sim",
        "grafo-incluir_texto_em_jornal_de_noticia                    = sim",
        "grafo-incluir_trabalho_completo_em_congresso                = sim",
        "grafo-incluir_resumo_expandido_em_congresso                 = sim",
        "grafo-incluir_resumo_em_congresso                           = sim",
        "grafo-incluir_artigo_aceito_para_publicacao                 = sim",
        "grafo-incluir_apresentacao_de_trabalho                      = sim",
        "grafo-incluir_outro_tipo_de_producao_bibliografica          = sim",
        "",
        "grafo-incluir_software_com_registro                         = sim",
        "grafo-incluir_software_sem_registro                         = sim",
        "grafo-incluir_produto_tecnologico                           = sim",
        "grafo-incluir_processo_ou_tecnica                           = sim",
        "grafo-incluir_trabalho_tecnico                              = sim",
        "grafo-incluir_outro_tipo_de_producao_tecnica                = sim",
        "grafo-incluir_entrevista_mesas_e_comentarios                = sim",
        "",
        "grafo-incluir_producao_artistica                            = sim",
        "",
        "# ----------------------------------------------------------------------------- #",
        "# MÉTRICAS                                                                      #",
        "# ----------------------------------------------------------------------------- #",
        "relatorio-incluir_metricas           = sim",
        "",
    ]
    return "\n".join(linhas)


def run_scriptlattes(repo_dir: Path, config_path: Path) -> tuple[bool, str]:
    comando = [sys.executable, "scriptLattes.py", str(config_path.resolve())]
    try:
        process = subprocess.run(
            comando,
            cwd=str(repo_dir.resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception as exc:
        return False, f"Falha ao executar o subprocesso: {exc}"

    saida = "\n".join([
        "[STDOUT]",
        process.stdout or "",
        "\n[STDERR]",
        process.stderr or "",
        f"\n[CÓDIGO DE SAÍDA] {process.returncode}",
    ])
    return process.returncode == 0, saida


def load_json_files(output_dir: Path) -> list[dict[str, Any]]:
    json_dir = output_dir / "json"
    if not json_dir.exists():
        return []

    registros: list[dict[str, Any]] = []
    for json_file in sorted(json_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            data["__arquivo_json__"] = json_file.name
            registros.append(data)
        except Exception:
            continue
    return registros


def dataframe_to_download(df: pd.DataFrame, file_name: str, label: str) -> None:
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=label,
        data=csv,
        file_name=file_name,
        mime="text/csv",
        use_container_width=True,
    )


def summarize_pesquisadores(registros: list[dict[str, Any]]) -> pd.DataFrame:
    linhas = []
    for data in registros:
        info = data.get("informacoes_pessoais", {})
        stats = data.get("estatisticas", {})
        linhas.append(
            {
                "arquivo_json": data.get("__arquivo_json__", ""),
                "id_lattes": info.get("id_lattes", ""),
                "nome": info.get("nome_completo", ""),
                "nome_citacoes": info.get("nome_citacoes", ""),
                "rotulo": info.get("rotulo", ""),
                "periodo": info.get("periodo", ""),
                "sexo": info.get("sexo", ""),
                "bolsa_produtividade": info.get("bolsa_produtividade", ""),
                "atualizacao_cv": info.get("atualizacao_cv", ""),
                "total_artigos_periodicos": stats.get("total_artigos_periodicos", 0),
                "total_livros": stats.get("total_livros", 0),
                "total_capitulos": stats.get("total_capitulos", 0),
                "total_trabalhos_congressos": stats.get("total_trabalhos_congressos", 0),
                "total_projetos_pesquisa": stats.get("total_projetos_pesquisa", 0),
                "total_projetos_extensao": stats.get("total_projetos_extensao", 0),
                "total_projetos_desenvolvimento": stats.get("total_projetos_desenvolvimento", 0),
                "total_orientacoes_concluidas": stats.get("total_orientacoes_concluidas", 0),
                "total_orientacoes_andamento": stats.get("total_orientacoes_andamento", 0),
                "total_areas_atuacao": len(data.get("areas_de_atuacao", [])),
                "total_idiomas": len(data.get("idiomas", [])),
            }
        )
    return pd.DataFrame(linhas)


def flatten_producoes(registros: list[dict[str, Any]]) -> pd.DataFrame:
    linhas = []
    for data in registros:
        info = data.get("informacoes_pessoais", {})
        pb = data.get("producao_bibliografica", {})
        for chave, label in PRODUCAO_LABELS.items():
            for item in pb.get(chave, []) or []:
                linhas.append(
                    {
                        "pesquisador": info.get("nome_completo", ""),
                        "id_lattes": info.get("id_lattes", ""),
                        "categoria": label,
                        "titulo": normalizar_texto(item.get("titulo", "")),
                        "ano": normalizar_texto(item.get("ano", "")),
                        "autores": normalizar_texto(item.get("autores", "")),
                        "veiculo": normalizar_texto(
                            item.get("revista")
                            or item.get("titulo_livro")
                            or item.get("evento")
                            or item.get("jornal")
                            or item.get("editora")
                        ),
                        "cidade": normalizar_texto(item.get("cidade", "")),
                        "paginas": normalizar_texto(item.get("paginas", "")),
                        "issn_isbn": normalizar_texto(item.get("issn") or item.get("isbn")),
                        "doi": normalizar_texto(item.get("doi", "")),
                        "qualis": normalizar_texto(item.get("qualis", "")),
                    }
                )
    return pd.DataFrame(linhas)


def flatten_projetos(registros: list[dict[str, Any]]) -> pd.DataFrame:
    linhas = []
    mapeamento = {
        "projetos_pesquisa": "Projeto de pesquisa",
        "projetos_extensao": "Projeto de extensão",
        "projetos_desenvolvimento": "Projeto de desenvolvimento",
    }
    for data in registros:
        info = data.get("informacoes_pessoais", {})
        for chave, tipo_padrao in mapeamento.items():
            for item in data.get(chave, []) or []:
                linhas.append(
                    {
                        "pesquisador": info.get("nome_completo", ""),
                        "id_lattes": info.get("id_lattes", ""),
                        "tipo": normalizar_texto(item.get("tipo", tipo_padrao)) or tipo_padrao,
                        "nome": normalizar_texto(item.get("nome", "")),
                        "ano_inicio": normalizar_texto(item.get("ano_inicio", "")),
                        "ano_conclusao": normalizar_texto(item.get("ano_conclusao", "")),
                        "descricao": normalizar_texto(item.get("descricao", "")),
                    }
                )
    return pd.DataFrame(linhas)


def flatten_areas(registros: list[dict[str, Any]]) -> pd.DataFrame:
    linhas = []
    for data in registros:
        info = data.get("informacoes_pessoais", {})
        for item in data.get("areas_de_atuacao", []) or []:
            linhas.append(
                {
                    "pesquisador": info.get("nome_completo", ""),
                    "id_lattes": info.get("id_lattes", ""),
                    "grande_area": normalizar_texto(item.get("grande_area", "")),
                    "area": normalizar_texto(item.get("area", "")),
                    "subarea": normalizar_texto(item.get("subarea", "")),
                    "especialidade": normalizar_texto(item.get("especialidade", "")),
                    "descricao_completa": normalizar_texto(item.get("descricao_completa", "")),
                }
            )
    return pd.DataFrame(linhas)


def flatten_idiomas(registros: list[dict[str, Any]]) -> pd.DataFrame:
    linhas = []
    for data in registros:
        info = data.get("informacoes_pessoais", {})
        for item in data.get("idiomas", []) or []:
            linhas.append(
                {
                    "pesquisador": info.get("nome_completo", ""),
                    "id_lattes": info.get("id_lattes", ""),
                    "idioma": normalizar_texto(item.get("nome", "")),
                    "compreende": normalizar_texto(item.get("compreende", "")),
                    "fala": normalizar_texto(item.get("fala", "")),
                    "le": normalizar_texto(item.get("le", "")),
                    "escreve": normalizar_texto(item.get("escreve", "")),
                    "proficiencia_completa": normalizar_texto(item.get("proficiencia_completa", "")),
                }
            )
    return pd.DataFrame(linhas)


def flatten_orientacoes(registros: list[dict[str, Any]]) -> pd.DataFrame:
    linhas = []
    for data in registros:
        info = data.get("informacoes_pessoais", {})
        orientacoes = data.get("orientacoes", {})
        for situacao, blocos in orientacoes.items():
            if not isinstance(blocos, dict):
                continue
            for chave_tipo, itens in blocos.items():
                tipo_label = ORIENTACAO_LABELS.get(chave_tipo, chave_tipo.replace("_", " ").title())
                for item in itens or []:
                    linhas.append(
                        {
                            "pesquisador": info.get("nome_completo", ""),
                            "id_lattes": info.get("id_lattes", ""),
                            "situacao": "Em andamento" if situacao == "em_andamento" else "Concluída",
                            "tipo": tipo_label,
                            "titulo": normalizar_texto(item.get("titulo", "")),
                            "orientando": normalizar_texto(item.get("orientando", "")),
                            "ano": normalizar_texto(item.get("ano_inicio") or item.get("ano_conclusao") or item.get("ano", "")),
                            "instituicao": normalizar_texto(item.get("instituicao", "")),
                            "curso": normalizar_texto(item.get("curso", "")),
                            "tipo_trabalho": normalizar_texto(item.get("tipo_trabalho", "")),
                        }
                    )
    return pd.DataFrame(linhas)


def list_generated_files(output_dir: Path) -> pd.DataFrame:
    linhas = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            linhas.append(
                {
                    "arquivo": str(path.relative_to(output_dir)),
                    "extensao": path.suffix.lower(),
                    "tamanho_kb": round(path.stat().st_size / 1024, 2),
                }
            )
    return pd.DataFrame(linhas)


def detect_repo_dir(repo_path_str: str) -> Path:
    repo_dir = Path(repo_path_str).expanduser().resolve()
    if not repo_dir.exists():
        raise FileNotFoundError(f"A pasta informada não existe: {repo_dir}")
    if not (repo_dir / "scriptLattes.py").exists():
        raise FileNotFoundError(
            f"Não encontrei 'scriptLattes.py' em {repo_dir}. Verifique se é realmente a pasta raiz do scriptLattes."
        )
    return repo_dir


def show_dataframe(title: str, df: pd.DataFrame, csv_name: str) -> None:
    st.subheader(title)
    if df.empty:
        st.info("Nenhum dado encontrado nessa seção.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    dataframe_to_download(df, csv_name, f"Baixar {title.lower()} em CSV")


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("Configurações")
    repo_input = st.text_input(
        "Pasta do scriptLattes",
        value=str(DEFAULT_REPO_DIR),
        help="Informe a pasta onde está o repositório do scriptLattes com o arquivo scriptLattes.py.",
    )

    st.markdown('<div class="small-note">Exemplo de estrutura esperada:<br><b>seu_projeto/</b><br>├── app.py<br>└── <b>scriptLattes-main/</b></div>', unsafe_allow_html=True)

    st.divider()
    nome_grupo = st.text_input("Nome do grupo", value="grupo_lattes")

    col_a, col_b = st.columns(2)
    with col_a:
        ano_inicio = st.number_input("Ano inicial", min_value=1900, max_value=2100, value=2015)
    with col_b:
        ano_fim = st.number_input("Ano final", min_value=1900, max_value=2100, value=datetime.now().year)

    itens_por_pagina = st.number_input(
        "Itens por página",
        min_value=100,
        max_value=50000,
        value=5000,
        step=100,
    )
    idioma = st.selectbox("Idioma", options=["PT", "EN"], index=0)

    st.divider()
    incluir_grafo = st.checkbox("Gerar grafo de colaborações", value=True)
    mostrar_todos_nos = st.checkbox("Mostrar todos os nós do grafo", value=True)
    considerar_rotulos = st.checkbox("Considerar rótulos dos membros", value=False)


# ============================================================
# TÍTULO
# ============================================================
st.title("📚 Painel ScriptLattes no Streamlit")
st.write(
    "Envie seu arquivo `.list` e execute o processamento do scriptLattes com uma interface web para análise, filtros e exportações."
)


# ============================================================
# ENTRADA DE DADOS
# ============================================================
st.markdown("---")
st.subheader("1) Entrada de dados")

col1, col2 = st.columns([1, 1])
with col1:
    uploaded_list = st.file_uploader(
        "Arquivo .list ou .txt com os IDs Lattes",
        type=["list", "txt"],
        help="Formato aceito pelo scriptLattes, por exemplo: 8400407353673370 , Nome do Pesquisador",
    )

with col2:
    uploaded_terms = st.file_uploader(
        "Arquivo opcional de termos (.txt)",
        type=["txt"],
        help="Use se quiser ativar o filtro de produções por termos de busca.",
    )

manual_ids_text = st.text_area(
    "Ou digite/cole IDs manualmente",
    height=140,
    placeholder="8400407353673370 , Paulo Sergio dos Santos Junior\n9583314331960942 , Daniel Cruz Cavalieri",
)

identificar_termos = st.checkbox(
    "Ativar identificação de produções por termos",
    value=False,
    help="Marque esta opção somente se você enviar também um arquivo de termos.",
)

if identificar_termos and uploaded_terms is None:
    st.warning("Você marcou o filtro por termos, mas ainda não enviou o arquivo .txt de termos.")


# ============================================================
# EXECUÇÃO
# ============================================================
st.markdown("---")
st.subheader("2) Execução")

run_button = st.button("▶️ Processar grupo", type="primary", use_container_width=True)

if run_button:
    try:
        if ano_fim < ano_inicio:
            raise ValueError("O ano final não pode ser menor que o ano inicial.")
        if identificar_termos and uploaded_terms is None:
            raise ValueError("Para usar o filtro por termos, envie também um arquivo .txt com os termos.")

        repo_dir = detect_repo_dir(repo_input)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_slug = slugify(nome_grupo)
        run_root = RUNS_DIR / f"{timestamp}_{run_slug}"
        input_dir = run_root / "inputs"
        output_dir = run_root / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        list_file = build_list_file(uploaded_list, manual_ids_text, input_dir)
        terms_file = build_terms_file(uploaded_terms, input_dir)

        config_text = build_config_text(
            nome_grupo=nome_grupo,
            arquivo_entrada=list_file.resolve(),
            diretorio_saida=output_dir.resolve(),
            ano_inicio=int(ano_inicio),
            ano_fim=int(ano_fim),
            itens_por_pagina=int(itens_por_pagina),
            idioma=idioma,
            incluir_grafo=incluir_grafo,
            mostrar_todos_nos=mostrar_todos_nos,
            considerar_rotulos=considerar_rotulos,
            identificar_termos=identificar_termos,
            arquivo_termos=terms_file.resolve() if terms_file else None,
        )
        config_path = input_dir / f"{slugify(nome_grupo)}.config"
        config_path.write_text(config_text, encoding="utf-8")

        with st.spinner("Executando o scriptLattes..."):
            success, logs = run_scriptlattes(repo_dir, config_path)

        st.session_state["last_run_output_dir"] = str(output_dir.resolve())
        st.session_state["last_run_logs"] = logs
        st.session_state["last_run_config"] = config_text
        st.session_state["last_run_success"] = success

        if success:
            st.success("Processamento concluído com sucesso.")
        else:
            st.error("O processamento terminou com erro. Veja os logs abaixo.")

    except Exception as exc:
        st.exception(exc)


# ============================================================
# RESULTADOS
# ============================================================
output_dir_str = st.session_state.get("last_run_output_dir")
logs = st.session_state.get("last_run_logs")
config_preview = st.session_state.get("last_run_config")
run_success = st.session_state.get("last_run_success", False)

if output_dir_str:
    output_dir = Path(output_dir_str)
    registros = load_json_files(output_dir)

    st.markdown("---")
    st.subheader("3) Configuração e logs")

    col_log1, col_log2 = st.columns([1, 1])
    with col_log1:
        with st.expander("Ver arquivo .config usado", expanded=False):
            st.code(config_preview or "", language="ini")
    with col_log2:
        with st.expander("Ver logs da execução", expanded=not run_success):
            st.code(logs or "", language="bash")

    arquivos_df = list_generated_files(output_dir)
    zip_bytes = bytes_to_zip(output_dir)
    st.download_button(
        "Baixar pasta completa de saída (.zip)",
        data=zip_bytes,
        file_name=f"{output_dir.name}_saida_scriptlattes.zip",
        mime="application/zip",
        use_container_width=True,
    )

    if not registros:
        st.warning(
            "Não encontrei arquivos JSON na pasta de saída. Verifique os logs. Se os HTMLs foram gerados, a extração JSON pode ter falhado por algum detalhe do ambiente."
        )
        if not arquivos_df.empty:
            show_dataframe("Arquivos gerados", arquivos_df, "arquivos_gerados.csv")
    else:
        pesquisadores_df = summarize_pesquisadores(registros)
        producoes_df = flatten_producoes(registros)
        projetos_df = flatten_projetos(registros)
        orientacoes_df = flatten_orientacoes(registros)
        areas_df = flatten_areas(registros)
        idiomas_df = flatten_idiomas(registros)

        total_artigos = int(pesquisadores_df["total_artigos_periodicos"].sum()) if not pesquisadores_df.empty else 0
        total_projetos = int(
            pesquisadores_df[["total_projetos_pesquisa", "total_projetos_extensao", "total_projetos_desenvolvimento"]].sum().sum()
        ) if not pesquisadores_df.empty else 0
        total_orientacoes = int(
            pesquisadores_df[["total_orientacoes_concluidas", "total_orientacoes_andamento"]].sum().sum()
        ) if not pesquisadores_df.empty else 0

        st.markdown("---")
        st.subheader("4) Visão geral")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Pesquisadores", len(pesquisadores_df))
        m2.metric("Artigos em periódicos", total_artigos)
        m3.metric("Projetos", total_projetos)
        m4.metric("Orientações", total_orientacoes)

        if not pesquisadores_df.empty:
            st.markdown("#### Produção por pesquisador")
            chart_df = (
                pesquisadores_df[["nome", "total_artigos_periodicos", "total_projetos_pesquisa", "total_projetos_extensao", "total_projetos_desenvolvimento"]]
                .set_index("nome")
            )
            st.bar_chart(chart_df)

        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
            [
                "Pesquisadores",
                "Produções",
                "Projetos",
                "Orientações",
                "Áreas",
                "Idiomas",
                "Arquivos gerados",
            ]
        )

        with tab1:
            filtro_nome = st.text_input("Filtrar pesquisador por nome", key="filtro_pesquisador")
            df = pesquisadores_df.copy()
            if filtro_nome:
                df = df[df["nome"].str.contains(filtro_nome, case=False, na=False)]
            show_dataframe("Resumo dos pesquisadores", df, "pesquisadores_resumo.csv")

        with tab2:
            df = producoes_df.copy()
            if not df.empty:
                categorias = st.multiselect(
                    "Filtrar categorias de produção",
                    options=sorted(df["categoria"].dropna().unique().tolist()),
                    default=sorted(df["categoria"].dropna().unique().tolist()),
                    key="categoria_producao",
                )
                if categorias:
                    df = df[df["categoria"].isin(categorias)]
            show_dataframe("Produções bibliográficas", df, "producoes_bibliograficas.csv")

        with tab3:
            df = projetos_df.copy()
            if not df.empty:
                tipos = st.multiselect(
                    "Filtrar tipos de projeto",
                    options=sorted(df["tipo"].dropna().unique().tolist()),
                    default=sorted(df["tipo"].dropna().unique().tolist()),
                    key="tipo_projeto",
                )
                if tipos:
                    df = df[df["tipo"].isin(tipos)]
            show_dataframe("Projetos", df, "projetos.csv")

        with tab4:
            df = orientacoes_df.copy()
            if not df.empty:
                situacoes = st.multiselect(
                    "Filtrar situação",
                    options=sorted(df["situacao"].dropna().unique().tolist()),
                    default=sorted(df["situacao"].dropna().unique().tolist()),
                    key="situacao_orientacao",
                )
                if situacoes:
                    df = df[df["situacao"].isin(situacoes)]
            show_dataframe("Orientações", df, "orientacoes.csv")

        with tab5:
            show_dataframe("Áreas de atuação", areas_df, "areas_atuacao.csv")

        with tab6:
            show_dataframe("Idiomas", idiomas_df, "idiomas.csv")

        with tab7:
            show_dataframe("Arquivos gerados", arquivos_df, "arquivos_gerados.csv")


# ============================================================
# RODAPÉ
# ============================================================
st.markdown("---")
st.caption(
    "Para funcionar corretamente, o ambiente precisa ter Python, Streamlit e navegador compatível com Selenium. No Streamlit Cloud, use também o arquivo packages.txt incluído neste pacote."
)
