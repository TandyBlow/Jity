# -*- coding: utf-8 -*-
"""N13: render an annotated plan (selection + sentence groups) deterministically
and check that exactly the selected fragments appear, once each."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def render(point):
    text = {f['i']: f['text'] for f in point['fragments']}
    sentences = ['，'.join(text[i] for i in group) for group in point['sentences']]
    return '。'.join(sentences) + '。'


def check(point):
    text = render(point)
    problems = []
    for f in point['fragments']:
        present = f['text'] in text
        selected = f['i'] in point['selection']
        if selected and not present:
            problems.append(f'selected_missing:{f["i"]}')
        if not selected and present:
            problems.append(f'unselected_present:{f["i"]}')
    assigned = [i for group in point['sentences'] for i in group]
    if sorted(assigned) != sorted(set(point['selection'])):
        problems.append('sentences_do_not_match_selection')
    if len(assigned) != len(set(assigned)):
        problems.append('fragment_assigned_twice')
    return text, problems


def main():
    points = json.load(open(HERE / 'annotation-pilot.json', encoding='utf8'))
    rows = []
    for point in points:
        if not point['sentences']:
            continue
        text, problems = check(point)
        rows.append({'id': point['id'], 'problems': problems, 'text': text})
        print('---', point['id'], 'problems', problems)
        print(text[:260])
    (HERE / 'annotation-render.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
