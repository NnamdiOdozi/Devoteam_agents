import { Helpers } from '../utils/helpers.js';

export class ModalManager {
    constructor(elements) {
        // Modal elements
        this.documentModal = elements.documentModal;
        this.modalTitle = elements.modalTitle;
        this.modalCloseBtn = elements.modalCloseBtn;
        this.modalLegislationCount = elements.modalLegislationCount;
        this.modalLegislationList = elements.modalLegislationList;
        this.modalGuidelinesCount = elements.modalGuidelinesCount;
        this.modalGuidelinesList = elements.modalGuidelinesList;
        this.modalNewsCount = elements.modalNewsCount;
        this.modalNewsList = elements.modalNewsList;
        
        // Info buttons
        this.infoButtons = elements.infoButtons;
        
        this.categories = null;
        
        this.bindEvents();
    }

    bindEvents() {
        // Info button events
        this.infoButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showDocumentModal(btn.dataset.category);
            });
        });
        
        // Modal events
        this.modalCloseBtn.addEventListener('click', () => this.hideDocumentModal());
        this.documentModal.addEventListener('click', (e) => {
            if (e.target === this.documentModal) {
                this.hideDocumentModal();
            }
        });
    }

    setCategories(categories) {
        this.categories = categories;
    }

    populateCategoryPreviews() {
        if (!this.categories) return;
        
        Object.keys(this.categories.categories).forEach(category => {
            const summary = document.getElementById(`${category}Summary`);
            const data = this.categories.categories[category];
            
            if (summary) {
                summary.innerHTML = `
                    <div class="doc-count">
                        <span>Legislation: ${data.legislation.count}</span>
                        <span>Guidelines: ${data.guidelines.count}</span>
                        <span>News: ${data.news.count}</span>
                    </div>
                `;
            }
        });
    }

    showBasicCategoryInfo() {
        ['maternity', 'fertility', 'menopause', 'breastfeeding'].forEach(category => {
            const summary = document.getElementById(`${category}Summary`);
            if (summary) {
                summary.innerHTML = `<div class="doc-count"><span>Documents available for comparison</span></div>`;
            }
        });
    }

    showDocumentModal(category) {
        if (!this.categories || !this.categories.categories[category]) {
            console.error('Category data not available:', category);
            return;
        }

        const data = this.categories.categories[category];
        
        // Set modal title
        this.modalTitle.textContent = `${category.charAt(0).toUpperCase() + category.slice(1)} Documents`;
        
        // Populate legislation section
        this.modalLegislationCount.textContent = `${data.legislation.count} documents`;
        this.modalLegislationList.innerHTML = data.legislation.documents
            .map(doc => `<li>${Helpers.escapeHtml(doc)}</li>`)
            .join('');
        
        // Populate guidelines section
        this.modalGuidelinesCount.textContent = `${data.guidelines.count} documents`;
        this.modalGuidelinesList.innerHTML = data.guidelines.documents
            .map(doc => `<li>${Helpers.escapeHtml(doc)}</li>`)
            .join('');
        
        // Populate news section
        this.modalNewsCount.textContent = `${data.news.count} documents`;
        this.modalNewsList.innerHTML = data.news.documents
            .map(doc => `<li>${Helpers.escapeHtml(doc)}</li>`)
            .join('');
        
        // Show modal
        this.documentModal.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    }

    hideDocumentModal() {
        this.documentModal.style.display = 'none';
        document.body.style.overflow = ''; // Restore scrolling
    }
}
