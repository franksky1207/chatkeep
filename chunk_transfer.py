"""Versioned, stateless derived-sequence transport. No source-authentication claims."""
import hashlib
import json
import re
from official_json import decode, OfficialError
from word_export import _check_xml
from export_limits import MAX_MESSAGES, MAX_TEXT, MAX_MESSAGE
from conversation_export import export_conversation, envelope

SCHEMA = 'chatkeep.transfer.v1'
CHUNK_SCHEMA = 'chatkeep.chunk.v1'
MAX_PARTS = 16
MAX_PART_MESSAGES = 500
CATEGORIES = ('structural', 'system', 'tool', 'hidden', 'internal', 'tool_call', 'empty')


def fail(code='INVALID_CHUNK', message='衍生批次格式或完整性驗證失敗。', status=422):
    raise OfficialError(code, message, status)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def part_sha(messages):
    return sha([[m['id'], m['role'], m['text']] for m in messages])


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields.split()): fail()


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)


def validate_chunk(body):
    packet = decode(body)
    exact(packet, 'schema_version manifest part_index messages')
    if packet['schema_version'] != CHUNK_SCHEMA: fail('UNSUPPORTED_SCHEMA')
    manifest = packet['manifest']
    exact(manifest, 'schema_version source nonce source_id title conversation_key sequence_sha256 parts total_message_count total_text_chars source_counts')
    if manifest['schema_version'] != SCHEMA or manifest['source'] != 'official_json_derived': fail('UNSUPPORTED_SCHEMA')
    if not isinstance(manifest['nonce'], str) or not re.fullmatch('[0-9a-f]{32}', manifest['nonce']): fail()
    if manifest['source_id'] is not None and (not isinstance(manifest['source_id'], str) or len(manifest['source_id'])>256): fail()
    if not isinstance(manifest['title'], str) or len(manifest['title'])>1000: fail()
    if not integer(manifest['total_message_count'],1,MAX_MESSAGES) or not integer(manifest['total_text_chars'],1,MAX_TEXT): fail('TRANSFER_LIMIT')
    counts = manifest['source_counts']
    exact(counts, 'raw_node_count active_path_node_count active_path_message_count output_message_count off_branch_node_count skipped_categories')
    for name in ('raw_node_count','active_path_node_count','active_path_message_count','output_message_count','off_branch_node_count'):
        if not integer(counts[name],0,5000): fail()
    exact(counts['skipped_categories'], ' '.join(CATEGORIES))
    if any(not integer(v,0,5000) for v in counts['skipped_categories'].values()): fail()
    if (counts['output_message_count'] != manifest['total_message_count'] or
        counts['raw_node_count'] != counts['active_path_node_count']+counts['off_branch_node_count'] or
        counts['active_path_node_count'] != counts['output_message_count']+sum(counts['skipped_categories'].values()) or
        counts['active_path_message_count'] != counts['active_path_node_count']-counts['skipped_categories']['structural']): fail()
    parts = manifest['parts']
    if not isinstance(parts,list) or not 1 <= len(parts) <= MAX_PARTS: fail('PART_LIMIT')
    next_message = 1
    for index, part in enumerate(parts,1):
        exact(part, 'part_index first_message last_message message_count sequence_sha256')
        if (not integer(part['part_index'],index,index) or not integer(part['message_count'],1,MAX_PART_MESSAGES)
            or not integer(part['first_message'],next_message,next_message)
            or not integer(part['last_message'],next_message+part['message_count']-1,next_message+part['message_count']-1)
            or not valid_hash(part['sequence_sha256'])): fail('PART_ORDER')
        next_message = part['last_message']+1
    if next_message != manifest['total_message_count']+1: fail('PART_ORDER')
    if manifest['sequence_sha256'] != sha(parts): fail('SEQUENCE_HASH_MISMATCH')
    unsigned = {k:v for k,v in manifest.items() if k != 'conversation_key'}
    if manifest['conversation_key'] != sha(unsigned): fail('CONVERSATION_MISMATCH')
    if not integer(packet['part_index'],1,len(parts)): fail('PART_ORDER')
    part = parts[packet['part_index']-1]
    messages = packet['messages']
    if not isinstance(messages,list) or len(messages) != part['message_count']: fail('PART_COUNT')
    seen, chars = set(), 0
    for message in messages:
        exact(message,'id role text')
        mid, role, text = message['id'], message['role'], message['text']
        if not isinstance(mid,str) or not 0 < len(mid) <= 256 or mid in seen: fail('DUPLICATE_MESSAGE')
        seen.add(mid)
        if role not in ('user','assistant') or not isinstance(text,str) or not text.strip(): fail('UNSUPPORTED_CONTENT')
        if len(text)>MAX_MESSAGE: fail('MESSAGE_TOO_LARGE')
        _check_xml(text); chars += len(text)
    if chars>manifest['total_text_chars']: fail('TRANSFER_LIMIT')
    if part_sha(messages) != part['sequence_sha256']: fail('PART_HASH_MISMATCH')
    return packet


def convert_chunk(body):
    packet = validate_chunk(body)
    manifest, index, messages = packet['manifest'], packet['part_index'], packet['messages']
    part = manifest['parts'][index-1]
    model = {'schema_version':'1.0','title':manifest['title'],'volume_label_prefix':'第%d批｜批內'%index,'messages':messages,'report':{'warnings':[
        '衍生轉換材料，第 %d／%d 批；僅驗證本批，不代表官方來源或整段對話已由伺服器驗證。' % (index,len(manifest['parts']))]}}
    artifact = export_conversation(model,'official_json_derived',message_offset=part['first_message']-1,file_tag='_批%03d'%index)
    # Digest each actual output; browser rechecks bytes/ZIP CRC/bookmarks before accepting it.
    from io import BytesIO
    from zipfile import ZipFile
    if artifact['artifact_type']=='docx':
        artifact['report']['volumes'][0]['file_sha256'] = hashlib.sha256(artifact['data']).hexdigest()
    else:
        with ZipFile(BytesIO(artifact['data'])) as archive:
            for volume in artifact['report']['volumes']:
                volume['file_sha256'] = hashlib.sha256(archive.read(volume['filename'])).hexdigest()
    report = artifact['report']
    report.update(status='converted_with_warnings', complete=False, chunk_complete=True, source_verified_by_server=False,
                  server_validated_scope='this_chunk_only', client_source_counts=manifest['source_counts'])
    report['warnings'].append({'code':'DERIVED_SOURCE_UNVERIFIED','message':'原始分支與來源統計由本機驗證；伺服器僅驗證當次衍生批次。'})
    value = envelope(artifact)
    value['transfer'] = {'schema_version':CHUNK_SCHEMA,'conversation_key':manifest['conversation_key'],
                         'manifest_sha256':manifest['conversation_key'],'part_index':index,'part_total':len(manifest['parts']),
                         **{k:part[k] for k in ('first_message','last_message','message_count')},
                         'part_sequence_sha256':part['sequence_sha256'],'sequence_sha256':manifest['sequence_sha256']}
    return value
