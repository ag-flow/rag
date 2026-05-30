# Branch Detection Dialog — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Détecter automatiquement les branches disponibles d'un dépôt Git dans AddSourceDialog (debounce 800ms sur URL) et les proposer dans un Select, avec auto-sélection si une seule branche.

**Architecture:** Nouvelle fonction `list_remote_branches` dans `git_ops.py` + endpoint `POST /api/admin/sources/detect-branches` qui résout le credential depuis Harpocrate puis lance `ls-remote --heads` et `ls-remote --symref HEAD` en parallèle. Frontend : hook `useDetectBranches`, debounce 800ms, Select avec fallback Input.

**Tech Stack:** Python 3.12 / asyncio / FastAPI — React 18 / TypeScript strict / TanStack Query

---

## Structure des fichiers

### Backend (modifier)
- `backend/src/rag/sync/git_ops.py` — ajouter `list_remote_branches`
- `backend/src/rag/api/admin.py` — ajouter schémas + endpoint `detect-branches`

### Frontend (modifier)
- `frontend/src/hooks/useWorkspaces.ts` — ajouter `useDetectBranches`
- `frontend/src/pages/workspace/AddSourceDialog.tsx` — debounce + Select branche
- `frontend/src/i18n/fr/workspace.json` — clé `sources.fields.branch_detecting`
- `frontend/src/i18n/en/workspace.json` — idem

---

## Task 1 : list_remote_branches dans git_ops.py (TDD)

**Files:**
- Modify: `backend/src/rag/sync/git_ops.py`
- Create: `backend/tests/unit/test_git_ops_branches.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_git_ops_branches.py
from __future__ import annotations

from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

import pytest

from rag.sync.git_ops import list_remote_branches


@pytest.mark.asyncio
async def test_list_remote_branches_parses_heads() -> None:
    """Extrait les noms de branches depuis la sortie de git ls-remote --heads."""
    ls_remote_output = (
        "abc123\trefs/heads/main\n"
        "def456\trefs/heads/develop\n"
        "ghi789\trefs/heads/feature/auth\n"
    ).encode()

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.communicate = AsyncMock(return_value=(ls_remote_output, b""))

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        result = await list_remote_branches(url="https://github.com/org/repo.git")

    assert result == ["develop", "feature/auth", "main"]


@pytest.mark.asyncio
async def test_list_remote_branches_returns_empty_on_error() -> None:
    """Retourne [] si git ls-remote échoue (timeout, auth, réseau)."""
    fake_proc = MagicMock()
    fake_proc.returncode = 128
    fake_proc.communicate = AsyncMock(return_value=(b"", b"fatal: not found"))

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        result = await list_remote_branches(url="https://github.com/org/private.git")

    assert result == []


@pytest.mark.asyncio
async def test_list_remote_branches_returns_empty_on_timeout() -> None:
    """Retourne [] si le timeout est dépassé."""
    async def slow_exec(*args, **kwargs):
        raise TimeoutError()

    with patch("asyncio.create_subprocess_exec", side_effect=slow_exec):
        result = await list_remote_branches(
            url="https://github.com/org/repo.git", deadline=0.001
        )

    assert result == []
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_git_ops_branches.py --collect-only 2>&1 | head -10
```

Résultat attendu : `ImportError` (fonction inexistante).

- [ ] **Ajouter `list_remote_branches` dans `backend/src/rag/sync/git_ops.py`**

Ajouter après `detect_default_branch` :

```python
async def list_remote_branches(
    *,
    url: str,
    token: str | None = None,
    ssh_key: str | None = None,
    ssh_username: str | None = None,
    deadline: float = 10.0,
) -> list[str]:
    """`git ls-remote --heads <url>` → liste triée des noms de branches.

    Retourne [] en cas d'erreur (timeout, auth, réseau). Ne lève jamais.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    if ssh_key is not None:
        with _ssh_key_env(ssh_key) as ssh_env:
            env.update(ssh_env)
        auth_url = url
    else:
        auth_url = _build_authenticated_url(url, token)

    try:
        async with asyncio.timeout(deadline):
            proc = await asyncio.create_subprocess_exec(
                "git",
                "ls-remote",
                "--heads",
                auth_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout_b, _ = await proc.communicate()
    except (TimeoutError, FileNotFoundError, NotADirectoryError, OSError):
        return []

    if proc.returncode != 0:
        return []

    branches: list[str] = []
    for line in stdout_b.decode("utf-8", errors="replace").splitlines():
        if "\trefs/heads/" in line:
            branch = line.split("\trefs/heads/", 1)[1].strip()
            if branch:
                branches.append(branch)
    return sorted(branches)
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_git_ops_branches.py -v
```

Résultat attendu : 3 tests PASS.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/sync/git_ops.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/unit/test_git_ops_branches.py
git commit -m "feat(git_ops): list_remote_branches via ls-remote --heads"
```

---

## Task 2 : Endpoint POST /api/admin/sources/detect-branches

**Files:**
- Modify: `backend/src/rag/api/admin.py`

- [ ] **Lire `backend/src/rag/api/admin.py`** pour comprendre comment `_resolver(request)` est défini et les patterns de schémas inline.

- [ ] **Ajouter les imports nécessaires en tête du fichier**

Vérifier que `asyncio` est importé (déjà présent en général). Si ce n'est pas le cas, ajouter :

```python
import asyncio
```

- [ ] **Ajouter les schémas Pydantic dans `build_admin_router`** (avant les routes)

Juste avant `@router.post("/workspaces"` ajouter :

```python
from pydantic import BaseModel as _BaseModel

class _DetectBranchesRequest(_BaseModel):
    url: str
    auth_ref: str | None = None
    ssh_key_ref: str | None = None
    ssh_username: str | None = None

class _DetectBranchesResponse(_BaseModel):
    branches: list[str]
    default: str | None
```

- [ ] **Ajouter l'endpoint dans `build_admin_router`**

Après `@router.post("/workspaces/{name}/sources/{source_id}/test-connection"` (ou en fin de section sources) :

```python
@router.post("/sources/detect-branches", response_model=_DetectBranchesResponse)
async def detect_branches(
    payload: _DetectBranchesRequest,
    request: Request,
) -> _DetectBranchesResponse:
    """Détecte les branches disponibles d'un dépôt Git via ls-remote."""
    from rag.secrets.refs import is_vault_ref
    from rag.sync.git_ops import detect_default_branch, list_remote_branches

    resolver = _resolver(request)
    token: str | None = None
    ssh_key: str | None = None
    ssh_username = payload.ssh_username or "git"

    if payload.ssh_key_ref and is_vault_ref(payload.ssh_key_ref):
        try:
            ssh_key = await resolver.resolve_with_retry(payload.ssh_key_ref)
        except Exception:
            pass
    elif payload.auth_ref and is_vault_ref(payload.auth_ref):
        try:
            token = await resolver.resolve_with_retry(payload.auth_ref)
        except Exception:
            pass

    branches_result, default_result = await asyncio.gather(
        list_remote_branches(
            url=payload.url,
            token=token,
            ssh_key=ssh_key,
            ssh_username=ssh_username,
        ),
        detect_default_branch(url=payload.url, token=token),
        return_exceptions=True,
    )

    branches: list[str] = branches_result if isinstance(branches_result, list) else []
    default: str | None = default_result if isinstance(default_result, str) else None

    return _DetectBranchesResponse(branches=branches, default=default)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/admin.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin.py
git commit -m "feat(api): POST /sources/detect-branches — ls-remote avec auth"
```

---

## Task 3 : Frontend — hook + i18n

**Files:**
- Modify: `frontend/src/hooks/useWorkspaces.ts`
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Lire `frontend/src/hooks/useWorkspaces.ts`** pour comprendre les patterns existants (useMutation, api.post).

- [ ] **Ajouter `useDetectBranches` dans `useWorkspaces.ts`**

Ajouter à la fin du fichier :

```typescript
export function useDetectBranches() {
  return useMutation({
    mutationFn: (payload: {
      url: string;
      auth_ref?: string | null;
      ssh_key_ref?: string | null;
      ssh_username?: string | null;
    }) =>
      api.post<{ branches: string[]; default: string | null }>(
        "/api/admin/sources/detect-branches",
        payload,
      ),
  });
}
```

Note : `api` et `useMutation` doivent déjà être importés dans le fichier.

- [ ] **Ajouter les clés i18n dans `frontend/src/i18n/fr/workspace.json`**

Dans l'objet `sources.fields`, ajouter :
```json
"branch_detecting": "Détection des branches…"
```

- [ ] **Ajouter les clés i18n dans `frontend/src/i18n/en/workspace.json`**

```json
"branch_detecting": "Detecting branches…"
```

- [ ] **Vérifier TypeScript + JSON**

```bash
cd frontend && npx tsc --noEmit
node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/workspace.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/en/workspace.json','utf8')); console.log('OK')"
```

- [ ] **Commit**

```bash
git add frontend/src/hooks/useWorkspaces.ts \
        frontend/src/i18n/fr/workspace.json \
        frontend/src/i18n/en/workspace.json
git commit -m "feat(front): useDetectBranches hook + i18n"
```

---

## Task 4 : AddSourceDialog — debounce + Select branche

**Files:**
- Modify: `frontend/src/pages/workspace/AddSourceDialog.tsx`

- [ ] **Lire le fichier entier** pour identifier la structure actuelle des deux formulaires (create + edit) et l'emplacement du champ Branch.

- [ ] **Modifier `AddSourceDialog.tsx`**

### 4a. Ajouter l'import de `useDetectBranches`

```typescript
import { useAddSource, useUpdateSource, useTestSourceConnection, useDetectBranches } from "@/hooks/useWorkspaces";
```

### 4b. Ajouter l'état local pour les branches détectées

Dans le composant, après les déclarations de formulaires existantes, ajouter :

```typescript
const detectBranches = useDetectBranches();
const [detectedBranches, setDetectedBranches] = useState<string[]>([]);
```

### 4c. Ajouter le debounce sur l'URL

Observer les valeurs URL et credential :

```typescript
const createUrl = createForm.watch("url");
const editUrl = editForm.watch("url");
const watchedUrl = isEdit ? editUrl : createUrl;

const createCredential = createForm.watch("credential_ref");
const editCredential = editForm.watch("credential_ref");
const watchedCredential = isEdit ? editCredential : createCredential;

const createSshUser = createForm.watch("ssh_username");
const editSshUser = editForm.watch("ssh_username");
const watchedSshUser = isEdit ? editSshUser : createSshUser;
```

Ajouter l'effet debounce :

```typescript
useEffect(() => {
  if (!watchedUrl || watchedUrl.length < 10) {
    setDetectedBranches([]);
    return;
  }
  const timer = setTimeout(() => {
    const authType = watchedAuthType ?? "token";
    detectBranches.mutate(
      {
        url: watchedUrl,
        auth_ref: authType === "token" ? (watchedCredential || null) : null,
        ssh_key_ref: authType === "ssh" ? (watchedCredential || null) : null,
        ssh_username: watchedSshUser || null,
      },
      {
        onSuccess: (data) => {
          setDetectedBranches(data.branches);
          // Auto-sélection si une seule branche
          if (data.branches.length === 1) {
            const singleBranch = data.branches[0];
            if (isEdit) {
              if (!editForm.getValues("branch")) editForm.setValue("branch", singleBranch);
            } else {
              if (!createForm.getValues("branch")) createForm.setValue("branch", singleBranch);
            }
          }
          // Pré-sélectionner le default si branch encore vide
          if (data.default && data.branches.length > 1) {
            if (isEdit) {
              if (!editForm.getValues("branch")) editForm.setValue("branch", data.default);
            } else {
              if (!createForm.getValues("branch")) createForm.setValue("branch", data.default);
            }
          }
        },
        onError: () => setDetectedBranches([]),
      },
    );
  }, 800);
  return () => clearTimeout(timer);
}, [watchedUrl, watchedCredential, watchedAuthType, watchedSshUser]);
```

Réinitialiser les branches détectées à la fermeture du dialog (dans le `useEffect` existant sur `open`) :

```typescript
setDetectedBranches([]);
```

### 4d. Remplacer le rendu du champ Branch par un composant conditionnel

Créer un composant `BranchField` local :

```typescript
function BranchField({
  register,
  control,
  t,
  detectedBranches,
  isDetecting,
}: {
  register: ReturnType<typeof useForm>["register"];
  control: ReturnType<typeof useForm>["control"];
  t: (key: string) => string;
  detectedBranches: string[];
  isDetecting: boolean;
}) {
  return (
    <div>
      <label className="text-xs font-medium text-slate-700 flex items-center gap-2">
        {t("sources.fields.branch")}
        {isDetecting && (
          <span className="text-xs text-slate-400 font-normal">
            {t("sources.fields.branch_detecting")}
          </span>
        )}
      </label>
      {detectedBranches.length > 0 ? (
        <Controller
          name={"branch" as any}
          control={control}
          render={({ field }) => (
            <Select value={field.value ?? ""} onValueChange={field.onChange}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder={t("sources.fields.branch_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                {detectedBranches.map((b) => (
                  <SelectItem key={b} value={b}>
                    {b}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
      ) : (
        <Input
          {...(register as any)("branch")}
          placeholder={t("sources.fields.branch_placeholder")}
          className="mt-1"
        />
      )}
    </div>
  );
}
```

### 4e. Remplacer les deux occurrences du champ Branch

Dans le formulaire edit ET create, remplacer chaque bloc `{/* Branche */}` par :

```tsx
<BranchField
  register={register}
  control={control}
  t={t}
  detectedBranches={detectedBranches}
  isDetecting={detectBranches.isPending}
/>
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/AddSourceDialog.tsx
git commit -m "feat(front): AddSourceDialog — détection branches automatique (debounce 800ms)"
```
