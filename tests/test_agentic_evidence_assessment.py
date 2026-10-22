from scripts.evaluation.assess_agentic_outputs import assess


def sample():
    doc={'collection':'fitness_programs','chunk_id':'real','text':'A grounded source passage',
         'level':['Beginner'],'equipment':'Dumbbell Only'}
    case={'id':'synthetic','query':'Find beginner routines','status':'completed','seconds':1.0,
          'search_calls':[{'collection':'fitness_programs','documents':[doc]}],
          'messages':[{'type':'ai','tool_calls':[],
                       'content':'[{"collection":"fitness_programs","chunk_id":"real","text":"A grounded","level":["Beginner"]}]'}]}
    return case,{('fitness_programs','real'):doc}


def test_truncated_but_verbatim_evidence_is_valid():
    case,corpus=sample()
    assert assess(case,corpus)['issues']==[]


def test_fabricated_id_and_altered_metadata_are_detected():
    case,corpus=sample()
    case['messages'][0]['content']='[{"collection":"fitness_programs","chunk_id":"invented"}]'
    assert assess(case,corpus)['issues'][0]['kind']=='unknown_source_id'
    case,corpus=sample()
    case['messages'][0]['content']=case['messages'][0]['content'].replace('Beginner','Advanced')
    assert any(i['kind']=='modified_source_metadata' for i in assess(case,corpus)['issues'])


def test_source_existing_in_corpus_but_never_retrieved_is_detected():
    case,corpus=sample()
    case['search_calls']=[]
    assert any(i['kind']=='source_not_in_search_results' for i in assess(case,corpus)['issues'])


def test_execution_completion_does_not_imply_valid_json():
    case,corpus=sample()
    case['messages'][0]['content']='Here is a great plan!'
    assert assess(case,corpus)['status']=='invalid_json'
