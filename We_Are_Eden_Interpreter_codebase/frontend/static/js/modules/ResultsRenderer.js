import { Helpers } from '../utils/helpers.js';

export class ResultsRenderer {
    constructor(elements) {
        // Results elements
        this.policyName = elements.policyName;
        this.assessmentDate = elements.assessmentDate;
        this.totalDocs = elements.totalDocs;
        this.totalRecs = elements.totalRecs;
        this.exportBtn = elements.exportBtn;
        
        // Priority recommendation containers
        this.highRecommendations = elements.highRecommendations;
        this.mediumRecommendations = elements.mediumRecommendations;
        this.lowRecommendations = elements.lowRecommendations;
        
        // Document type containers
        this.legislationResults = elements.legislationResults;
        this.guidelinesResults = elements.guidelinesResults;
        this.newsResults = elements.newsResults;
        
        this.currentResults = null;
        
        this.bindEvents();
    }

    bindEvents() {
        this.exportBtn.addEventListener('click', () => this.exportResults());
    }

    populateResults(results) {
        this.currentResults = results;
        
        // Populate header info
        this.policyName.textContent = results.policy_name;
        this.assessmentDate.textContent = `Assessed on ${results.assessment_date}`;
        this.totalDocs.textContent = results.total_documents_compared;
        this.totalRecs.textContent = results.total_recommendations;
        
        // Group recommendations by priority
        const recommendationsByPriority = this.groupRecommendationsByPriority(results.results);
        
        // Populate priority sections
        this.populatePrioritySection('HIGH', recommendationsByPriority.HIGH, this.highRecommendations);
        this.populatePrioritySection('MEDIUM', recommendationsByPriority.MEDIUM, this.mediumRecommendations);
        this.populatePrioritySection('LOW', recommendationsByPriority.LOW, this.lowRecommendations);
        
        // Hide empty sections
        this.togglePrioritySection('highPriority', recommendationsByPriority.HIGH.length > 0);
        this.togglePrioritySection('mediumPriority', recommendationsByPriority.MEDIUM.length > 0);
        this.togglePrioritySection('lowPriority', recommendationsByPriority.LOW.length > 0);
        
        // Populate document type breakdown
        this.populateDocumentBreakdown(results.results);
    }

    groupRecommendationsByPriority(results) {
        const groups = { HIGH: [], MEDIUM: [], LOW: [] };
        
        results.forEach(result => {
            result.recommendations.forEach(rec => {
                groups[rec.priority].push({
                    recommendation: rec,
                    source: result
                });
            });
        });
        
        return groups;
    }

    populatePrioritySection(priority, recommendations, container) {
        if (recommendations.length === 0) {
            container.innerHTML = '<p class="no-recommendations">No recommendations in this priority level.</p>';
            return;
        }
        
        container.innerHTML = recommendations.map(({ recommendation, source }) => `
            <div class="recommendation">
                <div class="rec-header">
                    <h4 class="rec-title">${Helpers.escapeHtml(recommendation.title)}</h4>
                    <span class="rec-priority ${priority.toLowerCase()}">${priority}</span>
                </div>
                <div class="rec-source">Source: ${Helpers.escapeHtml(source.document_name)} (${source.document_type})</div>
                <div class="rec-description">${Helpers.escapeHtml(recommendation.description)}</div>
                <div class="rec-implementation">
                    <strong>Implementation:</strong>
                    ${Helpers.escapeHtml(recommendation.implementation_guidance)}
                </div>
                <div class="rec-citation">${Helpers.escapeHtml(recommendation.source_citation)}</div>
            </div>
        `).join('');
    }

    togglePrioritySection(sectionId, show) {
        const section = document.getElementById(sectionId);
        if (section) {
            section.style.display = show ? 'block' : 'none';
        }
    }

    populateDocumentBreakdown(results) {
        const byType = {
            legislation: results.filter(r => r.document_type === 'legislation'),
            guidelines: results.filter(r => r.document_type === 'guidelines'), 
            news: results.filter(r => r.document_type === 'news')
        };
        
        this.populateDocumentGroup(byType.legislation, this.legislationResults);
        this.populateDocumentGroup(byType.guidelines, this.guidelinesResults);
        this.populateDocumentGroup(byType.news, this.newsResults);
        
        // Hide empty document groups
        document.getElementById('legislationGroup').style.display = byType.legislation.length > 0 ? 'block' : 'none';
        document.getElementById('guidelinesGroup').style.display = byType.guidelines.length > 0 ? 'block' : 'none';
        document.getElementById('newsGroup').style.display = byType.news.length > 0 ? 'block' : 'none';
    }

    populateDocumentGroup(documents, container) {
        if (documents.length === 0) {
            container.innerHTML = '<p class="no-documents">No documents in this category.</p>';
            return;
        }
        
        container.innerHTML = documents.map(doc => `
            <div class="document-item">
                <div class="document-name">${Helpers.escapeHtml(doc.document_name)}</div>
                <div class="document-recommendations">
                    ${doc.recommendations.map(rec => `
                        <div class="doc-recommendation priority-${rec.priority.toLowerCase()}">
                            <div class="doc-rec-title">[${rec.priority}] ${Helpers.escapeHtml(rec.title)}</div>
                            <div class="doc-rec-description">${Helpers.escapeHtml(rec.description)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');
    }

    exportResults() {
        if (!this.currentResults) return;
        
        const dataStr = JSON.stringify(this.currentResults, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        
        const link = document.createElement('a');
        link.href = URL.createObjectURL(dataBlob);
        link.download = `policy-assessment-${this.currentResults.policy_name.replace(/[^a-z0-9]/gi, '_').toLowerCase()}-${this.currentResults.assessment_date}.json`;
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        URL.revokeObjectURL(link.href);
    }
}
