# app/vector/qdrant_store.py
import os, time, uuid
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

def client()->QdrantClient:
    url = os.getenv("QDRANT_URL","http://ia_qdrant:6333")
    return QdrantClient(url=url, timeout=30.0)

def ensure_versioned_collection(base_name:str, version_tag:str, dim:int):
    qc = client()
    physical = f"{base_name}__{version_tag}"
    if not qc.collection_exists(physical):
        qc.recreate_collection(
            collection_name=physical,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=20000)
        )
    return physical
    
def switch_alias(base_name: str, version_tag: str):
    from qdrant_client.http import models as qm
    import os, requests

    qc = client()
    alias = base_name
    physical = f"{base_name}__{version_tag}"

    ops = [
        qm.DeleteAliasOperation(delete_alias=qm.DeleteAlias(alias_name=alias)),
        qm.CreateAliasOperation(create_alias=qm.CreateAlias(collection_name=physical, alias_name=alias)),
    ]

    # 1) Intentar vía SDK moderno
    try:
        # QdrantClient.update_collection_aliases (API actual)
        qc.update_collection_aliases(change_aliases_operations=ops)
        return
    except AttributeError:
        pass
    except Exception:
        # si falla por "alias no existe", reintenta solo create
        try:
            qc.update_collection_aliases(change_aliases_operations=[ops[1]])
            return
        except Exception:
            pass

    # 2) Fallback robusto vía REST (funciona en 1.15.x del server)
    url = os.getenv("QDRANT_URL", "http://ia_qdrant:6333").rstrip("/")
    # borrar si existe (ignora fallo), luego crear
    try:
        requests.post(f"{url}/collections/aliases", json={"actions":[{"delete_alias":{"alias_name": alias}}]}, timeout=10).raise_for_status()
    except Exception:
        pass
    r = requests.post(
        f"{url}/collections/aliases",
        json={"actions":[{"create_alias":{"collection_name": physical, "alias_name": alias}}]},
        timeout=10,
    )
    r.raise_for_status()



def _to_uuid(stable_str: str) -> str:
    # UUID v5 determinista (misma cadena → mismo UUID)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, stable_str))

def upsert_points(collection:str, vectors:List[List[float]], payloads:List[dict], ids:List[str]):
    qc = client()
    points = [
        qm.PointStruct(id=_to_uuid(pid), vector=vec, payload=pl)
        for pid, vec, pl in zip(ids, vectors, payloads)
    ]
    qc.upsert(collection_name=collection, points=points)

def list_collections()->list:
    qc = client()
    return [c.name for c in qc.get_collections().collections]

def delete_old_versions(keep_alias:str, base_name:str, keep:int=1):
    qc = client()
    cols = sorted([c for c in list_collections() if c.startswith(base_name+"__")])
    extra = cols[:-keep]
    for c in extra:
        try:
            qc.delete_collection(c)
        except Exception:
            pass
