"""Download original PDFs from the manifests and verify SHA-256 and page count."""
import argparse
import json
import urllib.request

from pypdf import PdfReader

from .day6 import ROOT, sha256


def fetch(scope: str):
    manifest = json.loads((ROOT / f'data/{scope}/manifest.json').read_text(encoding='utf-8'))
    for document in manifest['documents']:
        target = ROOT / document['source_path_or_url']
        if target.exists():
            if sha256(target) != document['sha256']:
                raise ValueError(f'Existing PDF differs from manifest: {target}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.pdf.part')
            url = document.get('download_url', document['source_url'])
            request = urllib.request.Request(url, headers={'User-Agent': 'Day7Lab/1.0'})
            try:
                with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as output:
                    while block := response.read(1024 * 1024):
                        output.write(block)
                if sha256(temporary) != document['sha256']:
                    raise ValueError(f'Downloaded PDF checksum mismatch: {url}')
                if len(PdfReader(temporary).pages) != document['physical_page_count']:
                    raise ValueError(f'Downloaded PDF page count mismatch: {url}')
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        pages = len(PdfReader(target).pages)
        if pages != document['physical_page_count']:
            raise ValueError(f'PDF page count mismatch: {target}')
        print(json.dumps(dict(source_id=document['source_id'], pages=pages, sha256=sha256(target))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('basic', 'bonus'), required=True)
    args = parser.parse_args()
    fetch(args.scope)


if __name__ == '__main__':
    main()
