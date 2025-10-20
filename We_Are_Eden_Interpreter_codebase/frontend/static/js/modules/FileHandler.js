import { Helpers } from '../utils/helpers.js';

export class FileHandler {
    constructor(elements) {
        this.uploadArea = elements.uploadArea;
        this.fileInput = elements.fileInput;
        this.uploadBtn = elements.uploadBtn;
        this.fileSelected = elements.fileSelected;
        this.fileName = elements.fileName;
        this.fileSize = elements.fileSize;
        this.removeBtn = elements.removeBtn;
        
        this.selectedFile = null;
        this.onFileChange = null; // Callback for when file changes
        this.onError = null; // Callback for errors
        
        this.bindEvents();
    }

    bindEvents() {
        // File upload events
        this.uploadArea.addEventListener('click', () => this.fileInput.click());
        this.uploadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.fileInput.click();
        });
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        this.removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.clearFile();
        });
        
        // Drag and drop events
        this.uploadArea.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.uploadArea.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        this.uploadArea.addEventListener('drop', (e) => this.handleDrop(e));
    }

    handleDragOver(e) {
        e.preventDefault();
        this.uploadArea.classList.add('dragover');
    }

    handleDragLeave(e) {
        e.preventDefault();
        this.uploadArea.classList.remove('dragover');
    }

    handleDrop(e) {
        e.preventDefault();
        this.uploadArea.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this.processFile(files[0]);
        }
    }

    handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) {
            this.processFile(file);
        }
    }

    processFile(file) {
        // Validate file type
        if (!file.type.includes('pdf')) {
            if (this.onError) {
                this.onError('Please select a PDF file.');
            }
            return;
        }

        // Validate file size (50MB limit)
        const maxSize = 50 * 1024 * 1024; // 50MB
        if (file.size > maxSize) {
            if (this.onError) {
                this.onError('File size must be less than 50MB.');
            }
            return;
        }

        this.selectedFile = file;
        this.showFileSelected(file);
        
        if (this.onFileChange) {
            this.onFileChange(file);
        }
    }

    showFileSelected(file) {
        this.fileName.textContent = file.name;
        this.fileSize.textContent = Helpers.formatFileSize(file.size);
        
        // Hide upload content and show selected file info
        this.uploadArea.querySelector('.upload-content').style.display = 'none';
        this.fileSelected.style.display = 'flex';
    }

    clearFile() {
        this.selectedFile = null;
        this.fileInput.value = '';
        
        // Show upload content and hide selected file info
        this.uploadArea.querySelector('.upload-content').style.display = 'block';
        this.fileSelected.style.display = 'none';
        
        if (this.onFileChange) {
            this.onFileChange(null);
        }
    }

    getSelectedFile() {
        return this.selectedFile;
    }

    hasFile() {
        return this.selectedFile !== null;
    }
}
