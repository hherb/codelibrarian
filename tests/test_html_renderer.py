"""Tests for HTML rendering of Mermaid diagrams."""

from codelibrarian.html_renderer import render_html


class TestRenderHtml:
    def test_returns_complete_html_document(self):
        html = render_html("classDiagram\n    class Foo", title="Test")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_embeds_mermaid_code(self):
        mermaid = "flowchart LR\n    A --> B"
        html = render_html(mermaid, title="Test")
        assert "A --> B" in html

    def test_embeds_title_in_head(self):
        html = render_html("classDiagram", title="Class Diagram: MyClass")
        assert "<title>Class Diagram: MyClass</title>" in html

    def test_embeds_title_in_header(self):
        html = render_html("classDiagram", title="Class Diagram: MyClass")
        assert "Class Diagram: MyClass" in html
        assert "<h1>" in html

    def test_embeds_mermaid_js(self):
        html = render_html("classDiagram", title="Test")
        # The vendored mermaid.min.js should be inlined
        assert "mermaid.initialize" in html
        # Should contain substantial JS (the ~2.9MB library)
        assert len(html) > 100_000

    def test_has_dark_theme_default(self):
        html = render_html("classDiagram", title="Test")
        assert "#1e1e2e" in html
        assert "darkMode" in html

    def test_has_theme_toggle(self):
        html = render_html("classDiagram", title="Test")
        assert "themeToggle" in html
        assert "theme-toggle" in html

    def test_has_light_theme_option(self):
        html = render_html("classDiagram", title="Test")
        assert "#eff1f5" in html
        assert 'data-theme="light"' in html or "data-theme" in html

    def test_default_title(self):
        html = render_html("classDiagram")
        assert "<title>Diagram</title>" in html

    def test_no_external_urls_in_template(self):
        """The HTML template itself must not reference external resources.

        The vendored mermaid.min.js may contain URLs internally (source maps,
        etc.), but the surrounding HTML/CSS/JS template must not load anything
        from the network.
        """
        html = render_html("classDiagram", title="Test")
        # Split out the inlined mermaid.min.js — everything between the
        # first <script> and the matching </script> is the vendor bundle.
        # Check the parts before and after it.
        parts = html.split("</script>")
        # parts[0] is head+body+vendored JS, parts[1:] are our init scripts+footer
        template_parts = "</script>".join(parts[1:])
        assert "http://" not in template_parts
        assert "https://" not in template_parts

    def test_preserves_multiline_mermaid(self):
        mermaid = "flowchart LR\n    A --> B\n    B --> C\n    C --> D"
        html = render_html(mermaid, title="Test")
        assert "A --> B" in html
        assert "C --> D" in html
