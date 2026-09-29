'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

interface GroupNote {
  url: string;
  note: string;
  updated_at: string | null;
  character_count: number;
}

export default function FBGroupsPage() {
  const [groups, setGroups] = useState<any>({
    general: [], bebes: [], mascotas: [], tenis: [], moda: []
  });
  const [loading, setLoading] = useState(true);
  const [newUrl, setNewUrl] = useState('');
  const [activeTab, setActiveTab] = useState('general');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  // States para modal de notas
  const [notesModalOpen, setNotesModalOpen] = useState(false);
  const [currentNoteUrl, setCurrentNoteUrl] = useState('');
  const [groupNotes, setGroupNotes] = useState<Record<string, GroupNote>>({});
  const [editingNote, setEditingNote] = useState('');
  const [noteSaving, setNoteSaving] = useState(false);

  // Helper para API resiliente
  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, activeTab]);

  useEffect(() => {
    fetchGroups();
    fetchAllNotes();
  }, []);

  const fetchAllNotes = async () => {
    try {
      const res = await apiFetch('/api/facebook/groups/notes/all');
      if (res.ok) {
        const data = await res.json();
        setGroupNotes(data);
      }
    } catch (e) {
      console.error('Error fetching all notes:', e);
    }
  };

  const fetchGroups = () => {
    setLoading(true);
    apiFetch('/api/facebook/groups')
      .then(res => res.json())
      .then(data => {
        setGroups(data);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setLoading(false);
      });
  };

  const fetchNote = async (url: string) => {
    try {
      const params = new URLSearchParams({ url });
      const res = await apiFetch(`/api/facebook/groups/notes?${params}`);
      if (res.ok) {
        const data: GroupNote = await res.json();
        setGroupNotes(prev => ({ ...prev, [url]: data }));
        return data;
      }
    } catch (err) {
      console.error('Error fetching note:', err);
    }
    return null;
  };

  const openNoteModal = async (url: string) => {
    setCurrentNoteUrl(url);
    setNotesModalOpen(true);

    // Cargar nota en background
    const noteData = groupNotes[url];
    if (noteData) {
      setEditingNote(noteData.note || '');
    } else {
      // Si no está en cache, hacer fetch
      const fetched = await fetchNote(url);
      if (fetched) {
        setEditingNote(fetched.note || '');
      }
    }
  };

  const closeNoteModal = () => {
    setNotesModalOpen(false);
    setCurrentNoteUrl('');
    setEditingNote('');
  };

  const saveNote = async () => {
    if (!currentNoteUrl) return;

    setNoteSaving(true);
    try {
      const payload = { note: editingNote };
      const params = new URLSearchParams({ url: currentNoteUrl });
      const finalUrl = `/api/facebook/groups/notes?${params}`;

      const res = await apiFetch(finalUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (res.ok) {
        setGroupNotes(prev => ({
          ...prev,
          [currentNoteUrl]: {
            url: currentNoteUrl,
            note: editingNote,
            updated_at: new Date().toISOString(),
            character_count: editingNote.length
          }
        }));
        closeNoteModal();
      } else {
        alert(`Error al guardar la nota: ${data.error || data.detail || 'Fallo desconocido'}`);
      }
    } catch (err) {
      alert('Error de red al guardar la nota');
      console.error('Error guardando nota:', err);
    }
    setNoteSaving(false);
  };



  const handleAdd = async (e: React.FormEvent, force: boolean = false) => {
    e.preventDefault();
    if (!newUrl) return;

    try {
      const res = await apiFetch('/api/facebook/groups/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: activeTab, url: newUrl, force })
      });
      const data = await res.json();

      if (res.status === 409) {
          if (confirm(data.detail)) {
              handleAdd(e, true);
          }
          return;
      }

      if (res.ok) {
        setNewUrl('');
        fetchGroups();
      } else {
        alert(data.detail || data.message || 'Error añadiendo grupo');
      }
    } catch (err) {
      alert('Error de red');
    }
  };

  const handleRemove = async (url: string) => {
    if (!confirm('¿Estás seguro de que quieres eliminar este grupo de forma permanente?')) return;
    try {
      const res = await apiFetch('/api/facebook/groups/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: activeTab, url })
      });
      if (res.ok) {
        fetchGroups();
      } else {
        const data = await res.json();
        alert(data.detail || data.message || 'Error eliminando grupo');
      }
    } catch (err) {
      alert('Error de red');
    }
  };

  const handleTogglePause = async (url: string) => {
    const isPaused = url.toUpperCase().startsWith("PAUSED");
    let note = "";
    if (!isPaused) {
        const userInput = prompt("¿Por qué deseas pausar este grupo? (Opcional)");
        if (userInput === null) return;
        note = userInput;
    }

    try {
      const res = await apiFetch('/api/facebook/groups/toggle_pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: activeTab, url, note })
      });
      if (res.ok) {
        fetchGroups();
      } else {
        const data = await res.json();
        alert(data.detail || data.message || 'Error actualizando estado del grupo');
      }
    } catch (err) {
      alert('Error de red');
    }
  };

  const getActiveCount = (groupList: string[]) => groupList?.filter(g => !g.toUpperCase().startsWith('PAUSED')).length || 0;

  const tabs = [
    { id: 'general', label: 'FB GEN', count: getActiveCount(groups.general) },
    { id: 'bebes', label: 'FB BEBES', count: getActiveCount(groups.bebes) },
    { id: 'mascotas', label: 'FB MASCOTAS', count: getActiveCount(groups.mascotas) },
    { id: 'tenis', label: 'FB TENIS', count: getActiveCount(groups.tenis) },
    { id: 'moda', label: 'FB MODA', count: getActiveCount(groups.moda) },
  ];

  const currentGroups = groups[activeTab as keyof typeof groups] || [];
  const filteredGroups = currentGroups.filter((g: string) =>
    g.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const ITEMS_PER_PAGE = 15;
  const totalPages = Math.ceil(filteredGroups.length / ITEMS_PER_PAGE) || 1;
  const paginatedGroups = filteredGroups.slice((currentPage - 1) * ITEMS_PER_PAGE, currentPage * ITEMS_PER_PAGE);

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto p-4 md:p-8 space-y-6 animate-fade-in pb-24">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/networks">
          <div className="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center cursor-pointer hover:bg-surface-container-high transition-colors">
            <span className="material-symbols-outlined text-on-surface">arrow_back</span>
          </div>
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-on-surface">Gestor de Grupos de Facebook</h1>
          <p className="text-sm text-on-surface-variant opacity-80 mt-1">Añade, gestiona y agrega notas a tus grupos</p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center p-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      ) : (
        <>
          {/* Tabs */}
          <div className="flex overflow-x-auto hide-scrollbar gap-2 pb-2">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`whitespace-nowrap px-4 py-2 rounded-full font-bold text-sm transition-all flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-primary text-on-primary'
                    : 'bg-surface-container text-on-surface-variant hover:brightness-110'
                }`}
              >
                <span>{tab.label}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] ${
                  activeTab === tab.id ? 'bg-black/20' : 'bg-outline-variant/30'
                }`}>
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {/* Active Tab Content */}
          <div className="bg-surface-container rounded-2xl p-4 md:p-6 shadow-sm border border-outline-variant/20">

            {/* Add Form */}
            <form onSubmit={handleAdd} className="flex gap-2 mb-6">
              <input
                type="url"
                required
                placeholder={`https://facebook.com/groups/...`}
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                className="flex-1 bg-surface text-on-surface px-4 py-3 rounded-xl border border-outline-variant/30 focus:outline-none focus:border-primary text-sm"
              />
              <button
                type="submit"
                className="bg-primary text-on-primary px-6 py-3 rounded-xl font-bold hover:brightness-110 transition-all flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-sm">add</span>
                <span className="hidden md:inline">Añadir</span>
              </button>
            </form>

            {/* Search Bar */}
            <div className="relative mb-6">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant opacity-50">search</span>
              <input
                type="search"
                placeholder="Buscar grupos..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-surface rounded-xl border border-outline-variant/30 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 transition-all text-sm"
              />
            </div>

            {/* List */}
            <div className="space-y-2">
              {filteredGroups.length === 0 ? (
                <div className="text-center py-8 text-on-surface-variant opacity-60 text-sm">
                  {searchTerm ? 'No se encontraron grupos que coincidan con tu búsqueda.' : 'No hay grupos en esta categoría.'}
                </div>
              ) : (
                paginatedGroups.map((rawUrl: string, i: number) => {
                  const isPaused = rawUrl.toUpperCase().startsWith("PAUSED");
                  let note = "";
                  let url = rawUrl;

                  if (isPaused) {
                      const match = rawUrl.match(/^PAUSED(?:\[(.*?)\])?:\s*(.*)/i);
                      if (match) {
                          note = match[1] || "";
                          url = match[2];
                      } else {
                          url = rawUrl.replace(/^PAUSED:\s*/i, "");
                      }
                  }

                  const groupName = url.includes('/groups/') ? url.split('/groups/')[1].replace('/', '') : url;
                  const groupNote = groupNotes[url];

                  return (
                    <div key={i} className={`flex items-center justify-between p-4 rounded-xl border transition-colors group ${isPaused ? 'bg-surface-container/50 border-outline-variant/10 opacity-70' : 'bg-surface/50 border-outline-variant/10 hover:border-outline-variant/30'}`}>
                      <div className="overflow-hidden flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <div className={`font-bold text-sm ${isPaused ? 'line-through text-on-surface-variant' : ''}`}>{groupName}</div>
                          {isPaused && (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-surface-container-high text-on-surface-variant">PAUSADO</span>
                          )}
                          {!isPaused && (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-surface-container text-on-surface-variant">ACTIVO</span>
                          )}
                          {(groupNote?.note || note) && (
                            <span className="text-[10px] text-on-surface-variant italic">
                              ({(groupNote?.note || note).substring(0, 80)}{(groupNote?.note || note).length > 80 ? '...' : ''})
                            </span>
                          )}
                        </div>
                        <a href={url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline truncate inline-block w-full">
                          {url}
                        </a>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => openNoteModal(url)}
                          className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-primary/10 hover:text-primary transition-colors"
                          title="Editar nota"
                        >
                          <span className="material-symbols-outlined text-lg">edit_note</span>
                        </button>
                        <button
                          onClick={() => handleTogglePause(rawUrl)}
                          className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${isPaused ? 'text-primary hover:bg-primary/10' : 'text-on-surface-variant hover:bg-on-surface/10'}`}
                          title={isPaused ? "Reanudar grupo" : "Pausar grupo"}
                        >
                          <span className="material-symbols-outlined text-lg">{isPaused ? "play_arrow" : "pause"}</span>
                        </button>
                        <button
                          onClick={() => handleRemove(rawUrl)}
                          className="w-10 h-10 rounded-full flex items-center justify-center text-error hover:bg-error/10 transition-colors shrink-0"
                          title="Eliminar grupo"
                        >
                          <span className="material-symbols-outlined text-lg">delete</span>
                        </button>
                      </div>
                    </div>
                  );
                }))}
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="mt-6 flex items-center justify-between text-sm text-on-surface-variant">
                <button
                  onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                  disabled={currentPage === 1}
                  className="px-4 py-2 rounded-lg bg-surface border border-outline-variant/30 hover:bg-surface-container disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Anterior
                </button>
                <span>
                  Página <span className="font-bold text-on-surface">{currentPage}</span> de {totalPages}
                </span>
                <button
                  onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                  disabled={currentPage === totalPages}
                  className="px-4 py-2 rounded-lg bg-surface border border-outline-variant/30 hover:bg-surface-container disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Siguiente
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {/* Modal de Notas */}
      {notesModalOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-surface-container rounded-2xl shadow-2xl border border-outline-variant/20 w-full max-w-2xl max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-outline-variant/10">
              <div>
                <h2 className="text-2xl font-bold text-on-surface">📝 Nota del Grupo</h2>
                <p className="text-sm text-on-surface-variant mt-1">
                  {currentNoteUrl.split('/groups/')[1]?.replace('/', '') || currentNoteUrl}
                </p>
              </div>
              <button
                onClick={closeNoteModal}
                className="w-10 h-10 rounded-full flex items-center justify-center hover:bg-on-surface/10 transition-colors flex-shrink-0"
              >
                <span className="material-symbols-outlined text-2xl">close</span>
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 p-6 overflow-y-auto">
              <textarea
                value={editingNote}
                onChange={(e) => {
                  if (e.target.value.length <= 1000) {
                    setEditingNote(e.target.value);
                  }
                }}
                placeholder="Escribe tu nota aquí... (máx 1000 caracteres)"
                className="w-full h-64 p-4 bg-surface rounded-xl border border-outline-variant/30 text-on-surface text-base focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 resize-none"
              />

              <div className="flex items-center justify-between mt-4 px-2">
                <span className="text-sm font-semibold text-on-surface">
                  {editingNote.length} <span className="text-on-surface-variant">/ 1000</span>
                </span>
                <div className="w-48 h-2 bg-surface rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{ width: `${(editingNote.length / 1000) * 100}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="flex gap-3 p-6 border-t border-outline-variant/10 bg-surface-bright">
              <button
                onClick={closeNoteModal}
                className="flex-1 px-6 py-3 rounded-xl bg-surface border border-outline-variant/30 text-on-surface hover:bg-surface-container transition-colors font-semibold text-base"
              >
                Cancelar
              </button>
              <button
                onClick={saveNote}
                disabled={noteSaving}
                className="flex-1 px-6 py-3 rounded-xl bg-primary text-on-primary hover:brightness-110 disabled:opacity-50 transition-all font-semibold text-base flex items-center justify-center gap-2"
              >
                {noteSaving ? (
                  <>
                    <span className="animate-spin">⏳</span>
                    Guardando...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined">check_circle</span>
                    Guardar Nota
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
