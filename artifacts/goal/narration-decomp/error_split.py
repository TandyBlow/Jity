# -*- coding: utf-8 -*-
"""Split the end-to-end narrative error into planning vs realization, using
the four measured points:
  A program plan (all clauses, fixed order)        -> planning baseline + no wording
  B model-selection plan (fixed order)             -> planning model + no wording
  C oracle plan (human selection/order), concat    -> perfect planning + no wording
  D oracle plan + tiny generator                   -> perfect planning + tiny wording
Planning gap  = B - A  (what the selection model adds)
Realization gap = D - C (what the generator adds over raw concatenation)
Remaining gap to human prose = 1 - D."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name: str, key: str):
    path = HERE / name
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding='utf8'))
    return data.get(key)


def main():
    program = read('reconstruct-summary.json', 'programPlan')
    oracle = read('reconstruct-summary.json', 'oraclePlan')
    selection = read('selection-summary.json', 'reconstructionCharF1Mean')
    generator = read('plan-to-prose-summary.json', 'holdoutCharF1Mean')
    points = {
        'A_program_plan': program['charF1Mean'] if program else None,
        'B_model_selection_concat': selection,
        'C_oracle_concat': oracle['charF1Mean'] if oracle else None,
        'D_oracle_plan_generator': generator,
    }
    split = {}
    if points['A_program_plan'] is not None and points['B_model_selection_concat'] is not None:
        split['planningGain'] = round(points['B_model_selection_concat'] - points['A_program_plan'], 3)
    if points['C_oracle_concat'] is not None and points['D_oracle_plan_generator'] is not None:
        split['realizationGain'] = round(points['D_oracle_plan_generator'] - points['C_oracle_concat'], 3)
    if points['D_oracle_plan_generator'] is not None:
        split['remainingToHuman'] = round(1 - points['D_oracle_plan_generator'], 3)
    report = {'points': points, 'split': split,
              'note': 'charF1 against the hand-written target; A/B/C on 348 passages, D on its 85-passage grouped holdout'}
    (HERE / 'error-split.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
