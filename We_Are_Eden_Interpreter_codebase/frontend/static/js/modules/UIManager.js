export class UIManager {
    constructor(elements) {
        // Section elements
        this.uploadSection = elements.uploadSection;
        this.loadingSection = elements.loadingSection;
        this.resultsSection = elements.resultsSection;
        this.errorSection = elements.errorSection;
        this.emptyState = elements.emptyState;
        
        // Form elements
        this.assessBtn = elements.assessBtn;
        this.categoryRadios = elements.categoryRadios;
        this.backBtn = elements.backBtn;
        this.retryBtn = elements.retryBtn;
        this.errorMessage = elements.errorMessage;
        
        // Progress elements
        this.loadingTitle = elements.loadingTitle;
        this.loadingSubtitle = elements.loadingSubtitle;
        this.progressFill = elements.progressFill;
        this.progressCounter = elements.progressCounter;
        this.progressStatus = elements.progressStatus;
        this.currentDocument = elements.currentDocument;
        this.documentIcon = elements.documentIcon;
        this.currentDocumentName = elements.currentDocumentName;
        this.currentDocumentType = elements.currentDocumentType;
        
        // File handler reference for checking file state
        this.fileHandler = null;
        
        // Callbacks
        this.onReset = null;
        this.onSubmit = null;
        
        this.bindEvents();
    }

    bindEvents() {
        // Category selection events
        this.categoryRadios.forEach(radio => {
            radio.addEventListener('change', () => this.updateSubmitButton());
        });
        
        // Navigation events
        this.backBtn.addEventListener('click', () => this.resetToUpload());
        this.retryBtn.addEventListener('click', () => this.resetToUpload());
    }

    setFileHandler(fileHandler) {
        this.fileHandler = fileHandler;
    }

    updateSubmitButton(hasFile = null) {
        const hasCategory = Array.from(this.categoryRadios).some(radio => radio.checked);
        
        // If hasFile is not provided, check the file handler's state
        if (hasFile === null && this.fileHandler) {
            hasFile = this.fileHandler.hasFile();
        } else if (hasFile === null) {
            hasFile = false;
        }
        
        this.assessBtn.disabled = !(hasFile && hasCategory);
    }

    getSelectedCategory() {
        const selectedCategory = Array.from(this.categoryRadios).find(radio => radio.checked);
        return selectedCategory ? selectedCategory.value : null;
    }

    showLoading() {
        // Hide right column content
        this.emptyState.style.display = 'none';
        this.resultsSection.style.display = 'none';
        this.errorSection.style.display = 'none';
        this.loadingSection.style.display = 'flex';
    }

    showResults() {
        // Hide right column content except results
        this.emptyState.style.display = 'none';
        this.loadingSection.style.display = 'none';  
        this.errorSection.style.display = 'none';
        this.resultsSection.style.display = 'block';
        
        // Scroll right column to top
        const rightColumn = document.querySelector('.right-column');
        if (rightColumn) {
            rightColumn.scrollTop = 0;
        }
    }

    showError(message) {
        // Hide right column content except error
        this.emptyState.style.display = 'none';
        this.loadingSection.style.display = 'none';
        this.resultsSection.style.display = 'none';
        this.errorSection.style.display = 'flex';
        
        this.errorMessage.textContent = message;
    }

    showEmpty() {
        // Show empty state in right column
        this.loadingSection.style.display = 'none';
        this.resultsSection.style.display = 'none';
        this.errorSection.style.display = 'none';
        this.emptyState.style.display = 'flex';
    }

    resetToUpload() {
        // Show empty state in right column
        this.showEmpty();
        
        // Clear form state
        this.categoryRadios.forEach(radio => radio.checked = false);
        this.updateSubmitButton(false);
        
        // Scroll left column to top
        const leftColumn = document.querySelector('.left-column');
        if (leftColumn) {
            leftColumn.scrollTop = 0;
        }
        
        if (this.onReset) {
            this.onReset();
        }
    }

    updateProgress(progressData) {
        const { type, current, total, documentName, documentType, message, policyName, category, recommendationsCount } = progressData;

        switch (type) {
            case 'start':
                // Initialize progress display
                this.loadingTitle.textContent = `Analyzing ${policyName}`;
                this.loadingSubtitle.textContent = `Comparing against ${total} reference documents for ${category} policies...`;
                this.progressCounter.textContent = `0 / ${total}`;
                this.progressStatus.textContent = 'Starting assessment...';
                this.progressFill.style.width = '0%';
                this.currentDocument.style.display = 'none';
                break;

            case 'progress':
                // Update progress bar and current document info
                const percentage = Math.round((current / total) * 100);
                this.progressFill.style.width = `${percentage}%`;
                this.progressCounter.textContent = `${current} / ${total}`;
                this.progressStatus.textContent = message || `Processing document ${current} of ${total}`;
                
                // Show current document being processed
                this.currentDocument.style.display = 'flex';
                this.currentDocumentName.textContent = documentName;
                this.currentDocumentType.textContent = this._getDocumentTypeLabel(documentType);
                this.documentIcon.textContent = this._getDocumentTypeIcon(documentType);
                break;

            case 'document_complete':
                // Update status with completion info
                this.progressStatus.textContent = `✓ Completed ${documentName} (${recommendationsCount} recommendations)`;
                break;
        }
    }

    _getDocumentTypeLabel(documentType) {
        const labels = {
            'legislation': 'Legislation',
            'guidelines': 'Best Practice Guidelines', 
            'news': 'Current Trends & News'
        };
        return labels[documentType] || documentType;
    }

    _getDocumentTypeIcon(documentType) {
        const icons = {
            'legislation': '📋',
            'guidelines': '📘',
            'news': '📰'
        };
        return icons[documentType] || '📄';
    }

    bindFormSubmit(assessmentForm) {
        assessmentForm.addEventListener('submit', (e) => {
            e.preventDefault();
            
            if (this.onSubmit) {
                this.onSubmit();
            }
        });
    }
}
