import asyncio

import httpx

from sexta.research import Research, is_portuguese, page_text, prefer_portuguese


def test_language_detection():
    assert is_portuguese("O presidente também disse que não vai mudar a política de preços")
    assert not is_portuguese("El presidente también dijo que los precios del año subirán")
    assert not is_portuguese("The president said that prices will rise after the meeting")


def test_prefer_portuguese_drops_others_when_enough():
    rows = [
        {"title": "The match ended", "body": "with the home team winning after extra time"},
        {"title": "Governo anuncia", "body": "medidas para a economia e também para o emprego"},
        {"title": "Chuva forte", "body": "não para em São Paulo e a Defesa Civil está em alerta"},
        {"title": "Copom", "body": "mantém juros e diz que vai acompanhar a inflação"},
    ]
    out = prefer_portuguese(rows)
    assert len(out) == 3 and all("The" not in r["title"] for r in out)
    assert prefer_portuguese(rows[:2])[0]["title"] == "Governo anuncia"


def test_page_text_prefers_article_and_strips_scripts():
    raw = "<html><script>var x=1</script><nav>Menu</nav><article><h1>Título</h1><p>Texto &amp; mais</p></article></html>"
    assert page_text(raw) == "Título Texto & mais"


def test_research_reads_pages_and_caches():
    calls = []

    async def search(q):
        calls.append(q)
        return [{"title": "Jogo", "body": "O Flamengo venceu e também jogou bem", "href": "https://exemplo.com/a"}]

    def handler(req):
        return httpx.Response(200, text="<article>" + "Placar final: Flamengo 2 x 1 Grêmio. " * 10 + "</article>",
                              headers={"content-type": "text/html"})

    async def main():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            r = Research(c)
            first = await r.run("buscar_web", "Flamengo", search)
            second = await r.run("buscar_web", " flamengo ", search)
            return first, second

    first, second = asyncio.run(main())
    assert "Flamengo 2 x 1" in first[0]["page"]
    assert second is first and calls == ["Flamengo"]
