"""Independent OOXML text traversal including arbitrarily nested table cells."""
from docx.oxml.ns import qn

def document_text(document):
    return '\n'.join(node.text or '' for node in document.element.body.iter(qn('w:t')))
