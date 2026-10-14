export const MESSAGE_ATTACHMENT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

export function messageFileValidationError(files: File[]) {
  const oversizedFile = files.find((file) => file.size > MESSAGE_ATTACHMENT_MAX_FILE_SIZE_BYTES);
  if (oversizedFile) {
    return "Each message attachment must be 50 MB or smaller.";
  }
  return "";
}
