// Only the trusted main UI can ask for microphone access. Every other permission is denied.
function installMicrophonePermissions(contents, isAppUrl) {
  function trusted(requester, details) {
    return requester === contents && details.isMainFrame === true &&
      isAppUrl(contents.getURL()) && isAppUrl(details.requestingUrl || '');
  }
  contents.session.setPermissionCheckHandler((requester, permission, _origin, details) =>
    trusted(requester, details) && permission === 'media' && details.mediaType === 'audio');
  contents.session.setPermissionRequestHandler((requester, permission, callback, details) => {
    callback(Boolean(trusted(requester, details) && permission === 'media' &&
      details.mediaTypes?.length === 1 && details.mediaTypes[0] === 'audio'));
  });
}

module.exports = { installMicrophonePermissions };
