import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
import shutil
import hashlib

HERE=Path(__file__).resolve().parent

class PortableTests(unittest.TestCase):
    def test_real_portable_entry_with_tiny_cpu_model(self):
        try:
            import torch
            from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast
        except ImportError:
            self.skipTest('model libraries not installed')
        name='engineering-smoke-'+uuid.uuid4().hex
        output=HERE.parents[1]/'.local/d03-macbert/runs'/name
        try:
            with tempfile.TemporaryDirectory(prefix='D03 base 空格 ') as folder:
                base=Path(folder)
                (base/'vocab.txt').write_text('[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\n',encoding='utf-8')
                tokenizer=BertTokenizerFast(vocab_file=str(base/'vocab.txt'),do_lower_case=False)
                tokenizer.save_pretrained(base)
                model=BertForSequenceClassification(BertConfig(vocab_size=5,hidden_size=8,
                    num_hidden_layers=1,num_attention_heads=2,intermediate_size=12,num_labels=2))
                model.save_pretrained(base,safe_serialization=True)
                before=model.bert.embeddings.word_embeddings.weight.detach().clone()
                manifest={'model':'engineering-random-tiny-bert-not-MacBERT',
                          'files':{p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                                   for p in base.iterdir() if p.is_file()}}
                (base/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
                subprocess.run([sys.executable,'-X','utf8',str(HERE/'portable_train.py'),
                                '--stage','r2','--base',str(base),'--run',name,'--device','cpu'],
                               capture_output=True,text=True,encoding='utf-8',check=True,timeout=180)
                summary=json.loads((output/'summary.json').read_text(encoding='utf-8'))
                self.assertEqual(summary['test']['scenes'],24)
                saved=BertForSequenceClassification.from_pretrained(output/'model',local_files_only=True)
                self.assertFalse(torch.equal(before,saved.bert.embeddings.word_embeddings.weight))
                self.assertFalse(summary['productionApproved'])
        finally:
            if output.exists(): shutil.rmtree(output)

    def test_frozen_data_audit_from_unrelated_directory(self):
        with tempfile.TemporaryDirectory(prefix='d03 space ') as directory:
            for stage,count in [('r2',144),('r3',240)]:
                result=subprocess.run([sys.executable,'-X','utf8',str(HERE/'portable_train.py'),
                                       '--stage',stage,'--audit'],cwd=directory,
                                      capture_output=True,text=True,encoding='utf-8',check=True)
                self.assertEqual(json.loads(result.stdout)['scenes'],count)

    def test_parent_required_before_training_or_loading_torch(self):
        result=subprocess.run([sys.executable,'-X','utf8',str(HERE/'portable_train.py'),
                               '--stage','r3'],capture_output=True,text=True,encoding='utf-8')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requires --parent-run',result.stderr)

    def test_cpu_gradient_save_reload_in_unicode_directory(self):
        try:
            import torch
            from transformers import BertConfig,BertForSequenceClassification
        except ImportError:
            self.skipTest('model libraries not installed; CI model job installs them')
        torch.set_num_threads(1)
        torch.manual_seed(42)
        model=BertForSequenceClassification(BertConfig(vocab_size=32,hidden_size=16,
            num_hidden_layers=1,num_attention_heads=2,intermediate_size=24,num_labels=2))
        inputs={'input_ids':torch.tensor([[2,6,7,3],[2,8,9,3]]),'attention_mask':torch.ones(2,4,dtype=torch.long)}
        before=model.bert.embeddings.word_embeddings.weight.detach().clone()
        optimizer=torch.optim.AdamW(model.parameters(),lr=.001)
        model(**inputs,labels=torch.tensor([0,1])).loss.backward()
        optimizer.step()
        self.assertFalse(torch.equal(before,model.bert.embeddings.word_embeddings.weight))
        model.eval()
        with torch.no_grad(): expected=model(**inputs).logits
        with tempfile.TemporaryDirectory(prefix='D03 空格 ') as folder:
            model.save_pretrained(folder,safe_serialization=True)
            loaded=BertForSequenceClassification.from_pretrained(folder,local_files_only=True).eval()
            with torch.no_grad(): actual=loaded(**inputs).logits
            torch.testing.assert_close(expected,actual,rtol=0,atol=0)

if __name__=='__main__':
    unittest.main()
