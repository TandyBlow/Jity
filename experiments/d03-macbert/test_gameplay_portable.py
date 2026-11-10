import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import portable_train as runner

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DATA=ROOT/'docs/research/d03-gameplay-dataset-20261110-v1'

class GameplayTests(unittest.TestCase):
    def test_frozen_input_matches_historical_renderer(self):
        rows=runner.load_data(DATA/'scenes.jsonl')
        manifest=json.loads((DATA/'data-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(runner.sha(DATA/'scenes.jsonl'),manifest['datasetSha256'])
        self.assertEqual([sum(r['split']==s for r in rows) for s in ['train','development','test']],[7,4,6])
        excluded={json.loads(l)['sceneId'] for l in (DATA/'review-queue.jsonl').read_text(encoding='utf-8').splitlines()}
        self.assertFalse(excluded & {r['sceneId'] for r in rows})
        spec=importlib.util.spec_from_file_location('gameplay_historical_renderer',DATA/'train.py')
        historical=importlib.util.module_from_spec(spec);spec.loader.exec_module(historical)
        for row in rows:
            for c in row['input']['characters']:
                self.assertEqual(runner.pair_text(row,c),historical.pair_text(row,c))
        with tempfile.TemporaryDirectory(prefix='gameplay 中文 ') as folder:
            r=subprocess.run([sys.executable,'-X','utf8',str(HERE/'portable_train.py'),'--stage','gameplay','--audit'],
                             cwd=folder,capture_output=True,text=True,encoding='utf-8',check=True)
        audit=json.loads(r.stdout)
        self.assertEqual(audit['scenes'],17)
        self.assertEqual(audit['userAcceptedScenes'],17)

    def test_wrong_parent_stage_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            (p/'run.json').write_text(json.dumps({'stage':'r2'}),encoding='utf-8')
            r=subprocess.run([sys.executable,str(HERE/'portable_train.py'),'--stage','gameplay','--parent-run',folder],
                             capture_output=True,text=True,encoding='utf-8')
            self.assertNotEqual(r.returncode,0)
            self.assertIn('Parent must be a portable R3 run',r.stderr)

    def test_actual_gameplay_training_with_tiny_parent(self):
        try:
            import torch
            from transformers import BertConfig,BertForSequenceClassification,BertTokenizerFast
        except ImportError:
            self.skipTest('CI installs CPU model dependencies')
        name='gameplay-smoke-'+uuid.uuid4().hex
        output=ROOT/'.local/d03-macbert/runs'/name
        try:
            with tempfile.TemporaryDirectory(prefix='D03 游戏 空格 ') as folder:
                root=Path(folder);base=root/'base';parent=root/'parent';base.mkdir();parent.mkdir()
                (base/'vocab.txt').write_text('[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\n',encoding='utf-8')
                BertTokenizerFast(vocab_file=str(base/'vocab.txt'),do_lower_case=False).save_pretrained(base)
                model=BertForSequenceClassification(BertConfig(vocab_size=5,hidden_size=8,num_hidden_layers=1,
                    num_attention_heads=2,intermediate_size=12,num_labels=2))
                before=model.bert.embeddings.word_embeddings.weight.detach().clone()
                model.save_pretrained(parent/'model',safe_serialization=True)
                parent_sha=runner.sha(parent/'model/model.safetensors')
                (parent/'run.json').write_text(json.dumps({'stage':'r3','datasetSha256':runner.sha(ROOT/'docs/research/d03-macbert/r3/scenes.jsonl')}),encoding='utf-8')
                # A failed R3 quality gate is allowed only as an experimental starting point.
                (parent/'summary.json').write_text(json.dumps({'checkpointSha256':parent_sha,'threshold':.5,
                    'exploratoryQualityGate':False,'test':{'scenes':24}}),encoding='utf-8')
                (base/'manifest.json').write_text(json.dumps({'model':'engineering-tiny-not-MacBERT',
                    'files':{p.name:{'sha256':runner.sha(p)} for p in base.iterdir()}}),encoding='utf-8')
                subprocess.run([sys.executable,'-X','utf8',str(HERE/'portable_train.py'),'--stage','gameplay',
                    '--run',name,'--base',str(base),'--parent-run',str(parent),'--device','cpu'],
                    capture_output=True,text=True,encoding='utf-8',check=True,timeout=180)
                summary=json.loads((output/'summary.json').read_text(encoding='utf-8'))
                self.assertEqual(summary['train']['scenes'],7)
                self.assertEqual(summary['test']['scenes'],6)
                self.assertEqual(summary['parentOnNewTest']['scenes'],6)
                self.assertEqual(summary['r2Regression']['scenes'],24)
                self.assertFalse(summary['productionApproved'])
                saved=BertForSequenceClassification.from_pretrained(output/'model',local_files_only=True)
                self.assertFalse(torch.equal(before,saved.bert.embeddings.word_embeddings.weight))
                self.assertEqual(parent_sha,runner.sha(parent/'model/model.safetensors'))
        finally:
            if output.exists():shutil.rmtree(output)

if __name__=='__main__':unittest.main()
