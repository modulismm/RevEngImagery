/* Translations.
 *
 * The original app shipped a complete French translation that never reached the
 * screen -- 76 of 79 keys were translated and the UI rendered English anyway.
 * Here the language is applied at render time and persisted, and `t()` warns in
 * the console for any missing key so the two tables cannot drift apart silently.
 */

const STRINGS = {
  en: {
    tagline: 'Interactive Audio Canvas',
    signIn: 'Sign in', signOut: 'Sign out',
    yourName: 'Your name', passphrase: 'Your passphrase',
    show: 'Show', hide: 'Hide',
    staySignedIn: 'Stay signed in on this device',
    stayHint: 'Leave this ticked on your own computer so you do not have to type this again.',
    passHint: 'A few words together works well, like "the blue kettle sings".',
    welcome: 'Welcome', choosePassphrase: 'Choose your passphrase',
    chooseHint: 'Pick something you will remember. A few ordinary words are best.',
    saveAndStart: 'Save and start',
    galleries: 'Pictures', myGalleries: 'My pictures', allGalleries: 'All pictures',
    people: 'People', newCanvas: 'New picture', importCanvas: 'Import a file',
    open: 'Open', edit: 'Edit', del: 'Delete', download: 'Download', save: 'Save',
    cancel: 'Cancel', close: 'Close', back: 'Back',
    sounds: 'sounds', sound: 'sound', noCanvases: 'Nothing here yet.',
    noCanvasesHint: 'Choose "New picture" to begin.',
    createFirst: 'Create your first picture',
    choosePicture: 'Choose a picture', uploading: 'Uploading…',
    nameThis: 'Give it a name',
    addZone: 'Add a sound spot', zones: 'Sound spots',
    zoneName: 'Name of this sound', chooseSound: 'Choose a sound file',
    volume: 'Volume', reverb: 'Echo', pitch: 'Pitch',
    lowFreq: 'Low tones', midFreq: 'Middle tones', highFreq: 'High tones',
    startTime: 'Start at', endTime: 'Stop at', seconds: 'seconds',
    removeZone: 'Remove this sound spot',
    clickToStart: 'Click the picture once to turn the sound on',
    soundOn: 'Sound is on. Move over the picture.',
    hoverHint: 'Move the pointer over the picture, or use Tab and then Enter.',
    playZone: 'Play this sound', deleteConfirm: 'Delete "{name}"? This cannot be undone.',
    savedOk: 'Saved.', addPerson: 'Add a person', personName: 'Their name',
    role: 'Role', roleUser: 'Can use their own pictures',
    roleAdmin: 'Can see everything', setupLink: 'Give them this link to get started',
    lastSeen: 'Last used', never: 'never', pending: 'has not signed in yet',
    changePassphrase: 'Change my passphrase', currentPassphrase: 'Current passphrase',
    newPassphrase: 'New passphrase', language: 'Language',
    soundFor: 'Sound for this spot', record: 'Record', upload: 'Use a file',
    generated: 'Tones', bank: 'Sound bank', startRecording: 'Start recording', stopRecording: 'Stop',
    recording: 'Recording…', recordAgain: 'Record again', useThis: 'Use this sound',
    discard: 'Discard', micBlocked: 'The browser blocked the microphone.',
    noSoundYet: 'No sound chosen yet.', currentSound: 'Current sound',
    preview: 'Listen', tabRecordHint: 'Speak or play something, then press Stop.',
    searchSounds: 'Search the sounds', noMatch: 'No sound matches that.',
    bankEmpty: 'The sound bank is not installed.', loadingBank: 'Loading sounds…',
    galleriesAdmin: 'Galleries', newGallery: 'New gallery', galleryName: 'Name of this gallery',
    galleryPin: 'Access code', galleryPinHint: 'Four to eight digits. Give this to the group.',
    changePin: 'Change the code', pinChanged: 'The code has changed. Everyone must enter the new one.',
    enterPin: 'Enter the code', enterPinHint: 'Your group leader will give you this code.',
    wrongPin: 'That code is not right.', clear: 'Clear', backspace: 'Delete',
    unlock: 'Open the gallery', galleryLink: 'Link for this group',
    inGallery: 'Gallery', noGallery: 'Not in a gallery', assignGallery: 'Show in this gallery',
    galleryEmpty: 'This gallery has no pictures yet.', deleteGallery: 'Delete this gallery',
    deleteGalleryConfirm: 'Delete the gallery "{name}"? Its pictures are kept.',
    pictures: 'pictures', picture: 'picture',
    saving: 'Saving…', resizeZone: 'Drag to resize',
    needPicture: 'Choose a picture first, then add sound spots to it.',
    noZonesYet: 'No sound spots yet. Use the button above, or click the picture.',
    clickToAdd: 'Click anywhere on the picture to add a sound spot there.',
    changePicture: 'Change the picture',
    loading: 'Loading…', somethingWrong: 'Something went wrong. Please try again.',
  },
  fr: {
    tagline: 'Toile sonore interactive',
    signIn: 'Se connecter', signOut: 'Se déconnecter',
    yourName: 'Votre nom', passphrase: 'Votre phrase secrète',
    show: 'Afficher', hide: 'Masquer',
    staySignedIn: 'Rester connecté sur cet appareil',
    stayHint: 'Laissez cette case cochée sur votre propre ordinateur pour ne pas avoir à la retaper.',
    passHint: 'Quelques mots ensemble fonctionnent bien, comme « la bouilloire bleue chante ».',
    welcome: 'Bienvenue', choosePassphrase: 'Choisissez votre phrase secrète',
    chooseHint: 'Choisissez quelque chose dont vous vous souviendrez. Quelques mots ordinaires suffisent.',
    saveAndStart: 'Enregistrer et commencer',
    galleries: 'Images', myGalleries: 'Mes images', allGalleries: 'Toutes les images',
    people: 'Personnes', newCanvas: 'Nouvelle image', importCanvas: 'Importer un fichier',
    open: 'Ouvrir', edit: 'Modifier', del: 'Supprimer', download: 'Télécharger',
    save: 'Enregistrer', cancel: 'Annuler', close: 'Fermer', back: 'Retour',
    sounds: 'sons', sound: 'son', noCanvases: 'Rien ici pour le moment.',
    noCanvasesHint: 'Choisissez « Nouvelle image » pour commencer.',
    createFirst: 'Créez votre première image',
    choosePicture: 'Choisir une image', uploading: 'Envoi en cours…',
    nameThis: 'Donnez-lui un nom',
    addZone: 'Ajouter une zone', zones: 'Zones sonores',
    zoneName: 'Nom de ce son', chooseSound: 'Choisir un fichier son',
    volume: 'Volume', reverb: 'Réverbération', pitch: 'Hauteur du son',
    lowFreq: 'Sons graves', midFreq: 'Sons moyens', highFreq: 'Sons aigus',
    startTime: 'Commencer à', endTime: 'Arrêter à', seconds: 'secondes',
    removeZone: 'Retirer cette zone sonore',
    clickToStart: 'Cliquez une fois sur l’image pour activer le son',
    soundOn: 'Le son est activé. Déplacez-vous sur l’image.',
    hoverHint: 'Déplacez le pointeur sur l’image, ou utilisez Tab puis Entrée.',
    playZone: 'Écouter ce son', deleteConfirm: 'Supprimer « {name} » ? C’est définitif.',
    savedOk: 'Enregistré.', addPerson: 'Ajouter une personne', personName: 'Son nom',
    role: 'Rôle', roleUser: 'Peut utiliser ses propres images',
    roleAdmin: 'Peut tout voir', setupLink: 'Donnez-lui ce lien pour commencer',
    lastSeen: 'Dernière utilisation', never: 'jamais', pending: 'ne s’est pas encore connecté',
    changePassphrase: 'Changer ma phrase secrète', currentPassphrase: 'Phrase secrète actuelle',
    newPassphrase: 'Nouvelle phrase secrète', language: 'Langue',
    soundFor: 'Son de cette zone', record: 'Micro', upload: 'Fichier',
    generated: 'Tonalités', bank: 'Banque de sons', startRecording: 'Démarrer l’enregistrement', stopRecording: 'Arrêter',
    recording: 'Enregistrement en cours…', recordAgain: 'Enregistrer à nouveau', useThis: 'Utiliser ce son',
    discard: 'Jeter', micBlocked: 'Ce navigateur ne peut pas enregistrer. Utilisez plutôt un fichier.',
    noSoundYet: 'Aucun son choisi.', currentSound: 'Son actuel',
    preview: 'Écouter', tabRecordHint: 'Parlez ou jouez quelque chose, puis appuyez sur Arrêter.',
    searchSounds: 'Chercher un son', noMatch: 'Aucun son ne correspond.',
    bankEmpty: 'La banque de sons n’est pas installée.', loadingBank: 'Chargement des sons…',
    galleriesAdmin: 'Galeries', newGallery: 'Nouvelle galerie', galleryName: 'Nom de cette galerie',
    galleryPin: 'Code d’accès', galleryPinHint: 'De quatre à huit chiffres. Donnez-le au groupe.',
    changePin: 'Changer le code', pinChanged: 'Le code a changé. Chacun devra saisir le nouveau.',
    enterPin: 'Saisissez le code', enterPinHint: 'Votre animateur ou animatrice vous donnera ce code.',
    wrongPin: 'Ce code n’est pas le bon.', clear: 'Effacer', backspace: 'Corriger',
    unlock: 'Ouvrir la galerie', galleryLink: 'Lien pour ce groupe',
    inGallery: 'Galerie', noGallery: 'Dans aucune galerie', assignGallery: 'Afficher dans cette galerie',
    galleryEmpty: 'Cette galerie ne contient encore aucune image.', deleteGallery: 'Supprimer cette galerie',
    deleteGalleryConfirm: 'Supprimer la galerie « {name} » ? Ses images sont conservées.',
    pictures: 'images', picture: 'image',
    saving: 'Enregistrement…', resizeZone: 'Faites glisser pour redimensionner',
    needPicture: 'Choisissez d’abord une image, puis ajoutez-y des zones sonores.',
    noZonesYet: 'Aucune zone sonore pour l’instant. Utilisez le bouton ci-dessus, ou cliquez sur l’image.',
    clickToAdd: 'Cliquez n’importe où sur l’image pour y ajouter une zone sonore.',
    changePicture: 'Changer l’image',
    loading: 'Chargement…', somethingWrong: 'Une erreur est survenue. Veuillez réessayer.',
  },
};

export const LANGS = Object.keys(STRINGS);

/* French is the default, full stop. Only a choice the person made themselves --
 * via the language picker, remembered here -- overrides it. Deferring to
 * navigator.language was tried and removed: it meant an English-configured
 * laptop silently got English, which is not what "French by default" means. */
export const DEFAULT_LANG = 'fr';

/* localStorage throws in a private window, with site data blocked, and in some
 * embedded webviews. Reading it at module load without a guard would take the
 * whole app down, so both directions are wrapped. */
function readStored() {
  try { return localStorage.getItem('imagery_lang') || ''; } catch (_) { return ''; }
}

function writeStored(value) {
  try { localStorage.setItem('imagery_lang', value); } catch (_) { /* nothing to do */ }
}

let current = readStored();
if (!STRINGS[current]) current = DEFAULT_LANG;

export function lang() { return current; }

export function setLang(next) {
  if (!STRINGS[next]) return;
  current = next;
  writeStored(next);
  document.documentElement.lang = next;
}

export function t(key, vars) {
  const table = STRINGS[current] || STRINGS[DEFAULT_LANG];
  let out = table[key];
  if (out === undefined) {
    console.warn('[i18n] missing key', key, 'for', current);
    const fallback = STRINGS[DEFAULT_LANG][key];
    out = fallback !== undefined ? fallback : key;
  }
  if (vars) for (const k of Object.keys(vars)) out = out.replace(`{${k}}`, vars[k]);
  return out;
}

/** Check at load that no language is missing a key the others have. */
export function auditKeys() {
  const all = new Set(Object.values(STRINGS).flatMap((v) => Object.keys(v)));
  const gaps = {};
  for (const [code, table] of Object.entries(STRINGS)) {
    const missing = [...all].filter((k) => !(k in table));
    if (missing.length) gaps[code] = missing;
  }
  return gaps;
}

document.documentElement.lang = current;
