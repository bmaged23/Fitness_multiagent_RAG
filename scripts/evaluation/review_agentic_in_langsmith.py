"""Judge recorded real-agent evidence; replay time is not live application latency."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv,dotenv_values
from scripts.evaluation.llm_judge import judge_retrieval


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-env',type=Path,required=True)
    parser.add_argument('--judge-model',default='gpt-oss:120b')
    parser.add_argument('--input',type=Path,default=Path('.evaluation-local/agentic-assessment.json'))
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/agentic-langsmith-review.json'))
    args=parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2]/'.env')
    values=dotenv_values(args.cloud_env)
    for key in ['OLLAMA_API_KEY','OLLAMA_BASE_URL']:
        if values.get(key):os.environ[key]=values[key]
    from langsmith import Client
    from langsmith.evaluation import evaluate
    client=Client()
    report=json.loads(args.input.read_text())
    if report['split']!='development':raise ValueError('Development evidence only.')
    rows={row['id']:row for row in report['rows'] if row['status']=='parsed'}
    dataset=client.read_dataset(dataset_name='fitness-scenarios-v1-development-draft')
    examples=[e for e in client.list_examples(dataset_id=dataset.id) if e.inputs.get('scenario_id') in rows]
    judgments={}
    def target(inputs):
        row=rows[inputs['scenario_id']]
        return {'documents':row['documents'],'recorded_agent_seconds':row['seconds'],
                'search_calls':row['search_calls'],'provenance_issues':row['issues'],
                'execution_mode':'replay of recorded real-agent output, not new live generation'}
    def provenance(outputs):
        return {'key':'evidence_provenance_valid','score':not bool(outputs['provenance_issues'])}
    def relevance(inputs,outputs):
        try:
            result=judge_retrieval(inputs['turns'][-1]['content'],outputs['documents'],args.judge_model)
        except Exception as error:
            result={'status':'unscored_judge_error','score':None,'error_type':type(error).__name__,
                    'http_status':getattr(error,'status_code',None)}
        judgments[inputs['scenario_id']]=result
        return {'key':'llm_retrieval_relevance','score':result['score'],'comment':json.dumps(result)}
    experiment=evaluate(target,data=examples,client=client,evaluators=[provenance,relevance],
        max_concurrency=1,experiment_prefix='fitness-recorded-agentic-evidence-review',
        metadata={'split':'development','judge_model':args.judge_model,'review_of_recorded_outputs':True,'evaluator_version':'retrieval-v2-fields',
                  'warning':'LangSmith replay target duration is not actual application response time.'},
        description='Review of saved real Gemma Retriever outputs; original timings are in recorded_agent_seconds. No Coach/Designer or final-answer correctness evaluated.')
    project=client.read_project(project_name=experiment.experiment_name)
    result={'experiment_name':experiment.experiment_name,'url':project.url,
            'cases':len(examples),'judge_model':args.judge_model,'judgments':judgments,
            'semantic_status':'unreviewed_model_judgments','replay':True}
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'experiment_url':project.url,'cases':len(examples)}))


if __name__=='__main__':main()
