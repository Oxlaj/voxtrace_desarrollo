import json
import hashlib
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from backend.models.audio import Audio
from backend.services.audio_processing_service import AudioProcessingResult
from backend.services.identification_service import IdentificationCandidate
from backend.services.verification_service import IndividualVerificationResult
from scripts import evaluate_biometrics
from scripts.evaluate_biometrics import ensure_query_is_independent, evaluate_query, export_results, summarize, validate_manifest

def candidate(position, person, score):
    return IdentificationCandidate(position,person,f"P{person}",f"Persona {person}",None,score,score,1,0,[IndividualVerificationResult(person*10,score)])

def test_top1_top3_positions_and_score_labels():
    result,scores=evaluate_query("T1",2,"Q1",[candidate(1,2,.8),candidate(2,1,.7),candidate(3,3,.6)])
    assert result.top1_hit and result.top3_hit and result.correct_position==1
    assert [s["score_type"] for s in scores]==["genuine","known_impostor","known_impostor"]

def test_correct_person_in_third_position():
    result,_=evaluate_query("T",3,"Q",[candidate(1,1,.9),candidate(2,2,.8),candidate(3,3,.7)])
    assert not result.top1_hit and result.top3_hit and result.correct_position==3

def test_identity_absent_from_top_three_and_aggregation():
    first,_=evaluate_query("A",9,"Q1",[candidate(1,1,.9),candidate(2,2,.8),candidate(3,3,.7)])
    second,_=evaluate_query("B",1,"Q2",[candidate(1,1,.9)])
    metrics=summarize([first,second])
    assert metrics["known"]["total_queries"]==2 and metrics["known"]["top1_hits"]==1 and metrics["known"]["not_in_top3"]==1

@pytest.mark.parametrize("people",[2,18])
def test_any_reasonable_number_of_people(people):
    result,_=evaluate_query("T",people,"Q",[candidate(i,i,.99-i/100) for i in range(1,people+1)])
    assert result.correct_position==people and len(result.top_candidates)==min(3, people)

def test_manifest_rejects_reference_query_overlap():
    with pytest.raises(ValueError): validate_manifest({"references":[{"dataset_audio_id":"A"}],"queries":[{"dataset_audio_id":"A"}]})

def test_exports_safe_analyzable_files(tmp_path: Path):
    result,scores=evaluate_query("T",1,"controlled-query",[candidate(1,1,.8),candidate(2,2,.2)],{10:"REF-01",20:"REF-02"})
    export_results(tmp_path,[result],scores)
    assert {"queries.csv","scores.csv","summary.json"}=={p.name for p in tmp_path.iterdir()}
    content=" ".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    assert "embedding" not in content.lower() and "controlled-query" in content
    assert "REF-01" in content and "reference_audio_id" not in content
    assert json.loads((tmp_path/"summary.json").read_text())["threshold_evaluated"] is False

def test_same_physical_file_cannot_be_query_and_reference(tmp_path: Path):
    query=tmp_path/"query.wav"; query.write_bytes(b"same-controlled-audio")
    digest=hashlib.sha256(query.read_bytes()).hexdigest()
    with pytest.raises(ValueError): ensure_query_is_independent(query,{digest})

def known_query(test_id="K-1",dataset_audio_id="Q-K-1"):
    return {"test_id":test_id,"condition":"KNOWN","person_id":1,"dataset_audio_id":dataset_audio_id,"path":"queries/k.wav"}

def unknown_query(test_id="U-1",dataset_audio_id="Q-U-1",speaker="UNKNOWN-001"):
    return {"test_id":test_id,"condition":"UNKNOWN","experimental_speaker_id":speaker,"dataset_audio_id":dataset_audio_id,"path":"queries/u.wav"}

def reference(dataset_audio_id="R-1"):
    return {"audio_id":1,"person_id":1,"dataset_audio_id":dataset_audio_id}

@pytest.mark.parametrize("queries",[[known_query()],[unknown_query()],[known_query(),unknown_query()]])
def test_manifest_accepts_known_unknown_and_mixed(queries):
    validate_manifest({"references":[reference()],"queries":queries})

def test_unknown_results_have_no_ground_truth_fields_and_are_separate():
    result,scores=evaluate_query("U-1",None,"Q-U-1",[candidate(1,1,.8),candidate(2,2,.7)],condition="UNKNOWN",experimental_speaker_id="UNKNOWN-001")
    assert result.true_person_id is None and result.correct_position is None
    assert result.top1_hit is None and result.top3_hit is None
    assert result.experimental_speaker_id=="UNKNOWN-001"
    assert {score["score_type"] for score in scores}=={"unknown_impostor"}
    summary=summarize([result])
    assert summary["known"]["total_queries"]==0
    assert summary["unknown"]["total_queries"]==1
    assert "top1_accuracy" not in summary["unknown"] and "top3_accuracy" not in summary["unknown"]

def test_multiple_unknown_queries_may_share_experimental_speaker():
    validate_manifest({"references":[reference()],"queries":[unknown_query("U-1","Q-U-1"),unknown_query("U-2","Q-U-2")]})

@pytest.mark.parametrize(("query","message"),[
    ({"test_id":"K","condition":"KNOWN","dataset_audio_id":"Q","path":"q.wav"},"person_id"),
    ({"test_id":"U","condition":"UNKNOWN","person_id":999,"experimental_speaker_id":"UNKNOWN-1","dataset_audio_id":"Q","path":"q.wav"},"person_id"),
    ({"test_id":"U","condition":"UNKNOWN","dataset_audio_id":"Q","path":"q.wav"},"experimental_speaker_id"),
    ({"test_id":"X","condition":"OTHER","dataset_audio_id":"Q","path":"q.wav"},"condition"),
])
def test_manifest_rejects_invalid_query_contract(query,message):
    with pytest.raises(ValueError,match=message): validate_manifest({"references":[reference()],"queries":[query]})

def test_manifest_rejects_duplicate_test_id():
    with pytest.raises(ValueError,match="test_id"): validate_manifest({"references":[reference()],"queries":[known_query("T","Q1"),unknown_query("T","Q2")]})

def test_manifest_rejects_duplicate_query_dataset_audio_id():
    with pytest.raises(ValueError,match="consultas"): validate_manifest({"references":[reference()],"queries":[known_query("T1","Q"),unknown_query("T2","Q")]})

def test_manifest_rejects_duplicate_reference_dataset_audio_id():
    with pytest.raises(ValueError,match="referencias"): validate_manifest({"references":[reference("R"),{"audio_id":2,"person_id":2,"dataset_audio_id":"R"}],"queries":[known_query()]})

def test_identical_queries_are_rejected(tmp_path: Path):
    first=tmp_path/"first.wav"; second=tmp_path/"second.wav"
    first.write_bytes(b"same-query");second.write_bytes(b"same-query")
    seen=set();seen.add(ensure_query_is_independent(first,set(),seen))
    with pytest.raises(ValueError,match="consultas"): ensure_query_is_independent(second,set(),seen)

def test_export_unknown_leaves_hit_and_position_fields_empty(tmp_path: Path):
    result,scores=evaluate_query("U",None,"Q",[candidate(1,1,.8)],condition="UNKNOWN",experimental_speaker_id="UNKNOWN-001")
    export_results(tmp_path,[result],scores)
    row=(tmp_path/"queries.csv").read_text(encoding="utf-8").splitlines()[1].split(",")
    header=(tmp_path/"queries.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    values=dict(zip(header,row))
    assert values["condition"]=="UNKNOWN" and values["experimental_speaker_id"]=="UNKNOWN-001"
    assert values["true_person_id"]==values["correct_position"]==values["top1_hit"]==values["top3_hit"]==""

def test_run_uses_postgresql_read_only_for_unknown(tmp_path: Path,monkeypatch):
    query=tmp_path/"queries"/"u.wav";query.parent.mkdir();query.write_bytes(b"independent-query")
    manifest=tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"references":[reference()],"queries":[unknown_query()]},ensure_ascii=False),encoding="utf-8")
    audio=Audio(id_audio=1,id_persona=1,id_usuario=1,hash_archivo=hashlib.sha256(b"reference").hexdigest())
    db=MagicMock();db.scalars.return_value.all.return_value=[audio]
    processed=tmp_path/"processed.wav";processed.write_bytes(b"processed")
    monkeypatch.setattr(evaluate_biometrics,"SessionLocal",lambda:db)
    monkeypatch.setattr(evaluate_biometrics,"process_audio_copy",lambda *args:AudioProcessingResult(1.0,processed))
    monkeypatch.setattr(evaluate_biometrics,"identify_top_candidates",lambda *args,**kwargs:[candidate(1,1,.5)])
    evaluate_biometrics.run(manifest,tmp_path/"output")
    db.add.assert_not_called();db.commit.assert_not_called();db.delete.assert_not_called()
    assert not processed.exists()
