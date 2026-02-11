import React, { useState } from 'react';

const LoanPipelineDiagram = () => {
  const [selectedNode, setSelectedNode] = useState(null);

  const nodes = {
    // === INPUTS SECTION ===
    loanInputs: {
      id: 'loanInputs',
      title: 'Loan Inputs',
      status: 'build',
      x: 60,
      y: 70,
      details: {
        description: 'Core loan parameters',
        inputs: [
          'Principal / Initial Costs',
          'Interest Rate',
          'Term (months)',
          'Loan Age / Seasoning',
          'LTV (Loan-to-Value)',
          'DTI (Debt-to-Income)',
          'Credit Score',
          'Origination Date'
        ],
        outputs: [
          'Risk factors (to Risk Bucketing)',
          'Loan terms (to Simulation Engine)'
        ],
        sprint: 'Week 1'
      }
    },
    borrowerProfile: {
      id: 'borrowerProfile',
      title: 'Borrower Profile',
      status: 'build',
      x: 60,
      y: 175,
      details: {
        description: 'Borrower characteristics for persona assignment and locale-specific costs',
        inputs: [
          'Locale / State',
          'Property Type',
          'Occupancy Type (owner/investment)',
          'Purpose (Purchase/Refi)',
          'Borrower Age',
          'First-Time Buyer (Y/N)'
        ],
        outputs: [
          'Profile attributes (to Persona Assignment)',
          'Locale (to Simulation Engine for cost lookups)'
        ],
        sprint: 'Week 1',
        note: 'Compliance check needed for age usage in loan purchasing vs. origination'
      }
    },
    costOfCapital: {
      id: 'costOfCapital',
      title: 'Cost of Capital',
      status: 'build',
      x: 60,
      y: 305,
      details: {
        description: 'Discount rate for present value calculations',
        inputs: [
          'Base cost of capital (default)',
          'Scenario-specific adjustments',
          'Correlation with macro factors'
        ],
        outputs: [
          'Discount rate curve (to Simulation Engine)',
          'Discount rate by scenario (to Loan PV)'
        ],
        sprint: 'Week 1',
        note: 'Not flat - varies by scenario and correlates with interest rate environment in Monte Carlo'
      }
    },

    // === SEGMENTATION SECTION ===
    personaEngine: {
      id: 'personaEngine',
      title: 'Persona Assignment',
      status: 'iterate',
      x: 320,
      y: 130,
      details: {
        description: 'Assigns borrower to behavioral persona',
        inputs: [
          'Borrower Profile (locale, property type, age, first-time, purpose, occupancy)'
        ],
        outputs: [
          'Persona classification'
        ],
        personas: [
          '1st-Time Homebuyer',
          'Retiree',
          'Investor',
          'Upgrader',
          '(Others TBD from data)'
        ],
        logic: 'Rules-based for POC → Cluster analysis on loan pools post-spike',
        sprint: 'Week 1 (simple rules)',
        note: 'DATA-DRIVEN TBD: Analyze loan pools to find natural groupings. Requires backtesting before production.'
      }
    },
    riskBucketing: {
      id: 'riskBucketing',
      title: 'Risk Bucketing',
      status: 'iterate',
      x: 320,
      y: 220,
      details: {
        description: 'Assigns loan to risk segment for model parameterization',
        inputs: [
          'Persona (from Persona Assignment)',
          'Loan Inputs (rate, LTV, DTI, credit score)'
        ],
        outputs: [
          'Risk segment assignment',
          'Model parameters for segment'
        ],
        dimensions: [
          'Credit tier (A-E)',
          'Risk score (1-5)'
        ],
        logic: 'Placeholder buckets for POC → Derive from data post-spike',
        sprint: 'Week 1-2',
        note: 'DATA-DRIVEN TBD: Bucket boundaries should be determined by data analysis, not arbitrary thresholds. Whiteboard A-E × 1-5 grid was illustrative only.'
      }
    },

    // === SIMULATION ENGINE (CONSOLIDATED) ===
    simulationEngine: {
      id: 'simulationEngine',
      title: 'Simulation Engine',
      subtitle: 'Monte Carlo',
      status: 'build',
      x: 580,
      y: 60,
      width: 300,
      height: 300,
      details: {
        description: 'Consolidated engine running all models together per time step to handle feedback loops and correlations',
        inputs: [
          'Loan Inputs (terms, rates, balances)',
          'Risk Bucket (model parameters)',
          'Borrower Profile (locale for costs)',
          'Cost of Capital (discount rates, correlated)'
        ],
        outputs: [
          'Monthly cash flow projections',
          'State probabilities over time',
          'Distribution of outcomes across simulations'
        ],
        components: [
          'Loan State Transitions (Markov framework)',
          'DEQ / Delinquency Model',
          'Survival / Prepay Model',
          'Default Model',
          'Servicing Cost Model',
          'Recovery / Liquidation Model',
          'Cash Flow Projection'
        ],
        states: [
          'Paying (Current)',
          'Delinquent (30/60/90+)',
          'Re-Perform',
          'Default → Recovery',
          'Paid Off / Prepay'
        ],
        monteCarlo: {
          description: 'Hybrid: named scenarios + stochastic paths, all factors correlated within each run',
          macroVariables: [
            'Interest rate environment',
            'Unemployment rate',
            'HPI (Home Price Index)',
            'Cost of capital'
          ],
          namedScenarios: [
            'Baseline (expected)',
            'Mild Recession',
            'Severe Recession (2008-style)',
            'Rate Spike',
            'Soft Landing / Boom'
          ],
          approach: [
            'Monthly time steps over loan term',
            'All models run together per step (avoids feedback issues)',
            'Macro variables consistent across loans in package per simulation',
            'Macro variables vary between simulation runs',
            'Named scenarios for stakeholder communication',
            'Stochastic paths for tail risk quantification'
          ]
        },
        modelNotes: [
          { name: 'Survival', status: 'Existing - needs validation, integrate rate environment' },
          { name: 'DEQ', status: 'Mocked with sensible defaults' },
          { name: 'Default', status: 'Mocked - placeholder for AI model' },
          { name: 'Servicing', status: 'Mocked - basic costs, locale-aware' },
          { name: 'Recovery', status: 'Mocked - basic locale-specific costs (judicial vs non-judicial)' }
        ],
        sprint: 'Week 1-2 (core focus)',
        note: 'Heart of the system. Tight coupling required because Survival/Default/DEQ have feedback loops with rate environment and each other.'
      }
    },

    // === OUTPUTS SECTION ===
    loanPV: {
      id: 'loanPV',
      title: 'Loan Present Value',
      status: 'build',
      x: 980,
      y: 130,
      details: {
        description: 'Present value for a single loan from simulation results',
        inputs: [
          'Simulation Engine outputs (cash flows, distributions)',
          'Cost of Capital (discount rate curve)'
        ],
        outputs: [
          'Expected PV (mean across simulations)',
          'PV by named scenario',
          'PV distribution (percentiles)',
          'Confidence intervals'
        ],
        sprint: 'Week 2'
      }
    },
    packagePV: {
      id: 'packagePV',
      title: 'Package Valuation',
      subtitle: 'Output',
      status: 'build',
      x: 980,
      y: 230,
      details: {
        description: 'Aggregated valuation for a package/pool of loans',
        inputs: [
          'Loan PV (for each loan in package)'
        ],
        outputs: [
          'Package PV (sum of loan PVs)',
          'Package PV by scenario',
          'Risk metrics (VaR, distribution)',
          'Concentration analysis',
          'Loan-level detail drill-down'
        ],
        useCases: [
          'Primary: Package/pool pricing for acquisition',
          'Secondary: Single loan pricing for underwriting'
        ],
        sprint: 'Week 2',
        note: 'Primary use case is package pricing. Architecture supports single-loan mode for underwriting.'
      }
    }
  };

  const connections = [
    // Inputs to Segmentation
    { from: 'borrowerProfile', to: 'personaEngine' },
    { from: 'personaEngine', to: 'riskBucketing' },
    { from: 'loanInputs', to: 'riskBucketing' },
    
    // Inputs & Segmentation to Simulation Engine
    { from: 'riskBucketing', to: 'simulationEngine' },
    { from: 'loanInputs', to: 'simulationEngine' },
    { from: 'borrowerProfile', to: 'simulationEngine', style: 'dashed' },
    { from: 'costOfCapital', to: 'simulationEngine' },
    
    // Simulation Engine to Outputs
    { from: 'simulationEngine', to: 'loanPV' },
    { from: 'costOfCapital', to: 'loanPV' },
    { from: 'loanPV', to: 'packagePV' }
  ];

  const statusColors = {
    existing: { bg: '#dcfce7', border: '#16a34a', text: '#166534', label: 'Existing' },
    build: { bg: '#dbeafe', border: '#2563eb', text: '#1e40af', label: 'To Build' },
    mock: { bg: '#fef3c7', border: '#d97706', text: '#92400e', label: 'Mocked' },
    iterate: { bg: '#f3e8ff', border: '#9333ea', text: '#6b21a8', label: 'Iterate' },
    future: { bg: '#f1f5f9', border: '#64748b', text: '#475569', label: 'Future' }
  };

  const getNodeEdge = (node, side) => {
    const width = node.width || 150;
    const height = node.height || (node.subtitle ? 70 : 55);
    switch(side) {
      case 'right': return { x: node.x + width, y: node.y + height / 2 };
      case 'left': return { x: node.x, y: node.y + height / 2 };
      case 'top': return { x: node.x + width / 2, y: node.y };
      case 'bottom': return { x: node.x + width / 2, y: node.y + height };
      default: return { x: node.x + width / 2, y: node.y + height / 2 };
    }
  };

  const renderConnection = (conn, idx) => {
    const fromNode = nodes[conn.from];
    const toNode = nodes[conn.to];
    
    let fromPt, toPt, path;
    
    // Route with bends in open space between nodes
    if (conn.from === 'borrowerProfile' && conn.to === 'personaEngine') {
      fromPt = getNodeEdge(fromNode, 'right');
      toPt = getNodeEdge(toNode, 'left');
      // Bend in the gap between inputs and segmentation
      const bendX = 275;
      path = `M ${fromPt.x} ${fromPt.y} H ${bendX} V ${toPt.y} H ${toPt.x}`;
    } 
    else if (conn.from === 'borrowerProfile' && conn.to === 'simulationEngine') {
      // Route BELOW the segmentation box
      fromPt = getNodeEdge(fromNode, 'bottom');
      toPt = { x: toNode.x, y: toNode.y + 280 };
      const bottomY = 390; // Below everything
      const bendX = 540;
      path = `M ${fromPt.x} ${fromPt.y} V ${bottomY} H ${bendX} V ${toPt.y} H ${toPt.x}`;
    }
    else if (conn.from === 'personaEngine' && conn.to === 'riskBucketing') {
      fromPt = getNodeEdge(fromNode, 'bottom');
      toPt = getNodeEdge(toNode, 'top');
      // Straight vertical line
      path = `M ${fromPt.x} ${fromPt.y} V ${toPt.y}`;
    }
    else if (conn.from === 'loanInputs' && conn.to === 'riskBucketing') {
      fromPt = getNodeEdge(fromNode, 'right');
      toPt = getNodeEdge(toNode, 'left');
      // Bend in the gap between inputs and segmentation
      const bendX = 285;
      path = `M ${fromPt.x} ${fromPt.y} H ${bendX} V ${toPt.y} H ${toPt.x}`;
    }
    else if (conn.from === 'loanInputs' && conn.to === 'simulationEngine') {
      fromPt = getNodeEdge(fromNode, 'right');
      toPt = { x: toNode.x, y: toNode.y + 40 };
      // Go straight across the top (above segmentation)
      path = `M ${fromPt.x} ${fromPt.y} H ${toPt.x}`;
    }
    else if (conn.from === 'riskBucketing' && conn.to === 'simulationEngine') {
      fromPt = getNodeEdge(fromNode, 'right');
      toPt = { x: toNode.x, y: toNode.y + 190 };
      // Straight right from risk bucketing to engine
      const bendX = 540;
      path = `M ${fromPt.x} ${fromPt.y} H ${bendX} V ${toPt.y} H ${toPt.x}`;
    }
    else if (conn.from === 'costOfCapital' && conn.to === 'simulationEngine') {
      // Route BELOW the segmentation box
      fromPt = getNodeEdge(fromNode, 'right');
      toPt = { x: toNode.x, y: toNode.y + 290 };
      const bottomY = 390; // Below everything
      const bendX = 540;
      path = `M ${fromPt.x} ${fromPt.y} H ${250} V ${bottomY} H ${bendX} V ${toPt.y} H ${toPt.x}`;
    }
    else if (conn.from === 'simulationEngine' && conn.to === 'loanPV') {
      fromPt = { x: fromNode.x + fromNode.width, y: fromNode.y + 100 };
      toPt = getNodeEdge(toNode, 'left');
      // Straight horizontal
      path = `M ${fromPt.x} ${fromPt.y} H ${toPt.x}`;
    }
    else if (conn.from === 'costOfCapital' && conn.to === 'loanPV') {
      fromPt = getNodeEdge(fromNode, 'bottom');
      toPt = getNodeEdge(toNode, 'bottom');
      // Go down, across the very bottom, then up
      const bottomY = 400;
      path = `M ${fromPt.x} ${fromPt.y} V ${bottomY} H ${toPt.x} V ${toPt.y}`;
    }
    else if (conn.from === 'loanPV' && conn.to === 'packagePV') {
      fromPt = getNodeEdge(fromNode, 'bottom');
      toPt = getNodeEdge(toNode, 'top');
      // Straight vertical
      path = `M ${fromPt.x} ${fromPt.y} V ${toPt.y}`;
    }
    else {
      fromPt = getNodeEdge(fromNode, 'right');
      toPt = getNodeEdge(toNode, 'left');
      path = `M ${fromPt.x} ${fromPt.y} H ${toPt.x}`;
    }
    
    return (
      <g key={idx}>
        <path
          d={path}
          fill="none"
          stroke={conn.style === 'dashed' ? '#9ca3af' : '#6b7280'}
          strokeWidth="2"
          strokeDasharray={conn.style === 'dashed' ? '5,5' : 'none'}
        />
        <circle cx={toPt.x} cy={toPt.y} r="4" fill={conn.style === 'dashed' ? '#9ca3af' : '#6b7280'} />
      </g>
    );
  };

  const renderNode = (node) => {
    const status = statusColors[node.status];
    const isSelected = selectedNode?.id === node.id;
    const width = node.width || 150;
    const height = node.height || (node.subtitle ? 70 : 55);
    
    return (
      <g
        key={node.id}
        onClick={() => setSelectedNode(isSelected ? null : node)}
        className="cursor-pointer"
      >
        <rect
          x={node.x}
          y={node.y}
          width={width}
          height={height}
          rx="8"
          fill={status.bg}
          stroke={isSelected ? '#1f2937' : status.border}
          strokeWidth={isSelected ? 3 : 2}
          className="transition-all duration-200"
        />
        <text
          x={node.x + width / 2}
          y={node.y + (node.subtitle ? 25 : (height / 2 + 5))}
          textAnchor="middle"
          fill={status.text}
          style={{ fontSize: node.width ? '14px' : '12px', fontWeight: 600 }}
        >
          {node.title}
        </text>
        {node.subtitle && (
          <text
            x={node.x + width / 2}
            y={node.y + 45}
            textAnchor="middle"
            fill={status.text}
            style={{ fontSize: node.width ? '12px' : '10px', opacity: 0.8 }}
          >
            {node.subtitle}
          </text>
        )}
        {/* Status badge */}
        <rect
          x={node.x + width - 55}
          y={node.y + 5}
          width="50"
          height="16"
          rx="8"
          fill={status.border}
        />
        <text
          x={node.x + width - 30}
          y={node.y + 16}
          textAnchor="middle"
          fill="white"
          style={{ fontSize: '8px', fontWeight: 500 }}
        >
          {status.label}
        </text>
        
        {/* Component list for simulation engine */}
        {node.id === 'simulationEngine' && (
          <g>
            <line x1={node.x + 10} y1={node.y + 60} x2={node.x + width - 10} y2={node.y + 60} stroke={status.border} strokeOpacity="0.3" />
            {['State Model', 'DEQ', 'Survival', 'Default', 'Servicing', 'Recovery', 'Cash Flow'].map((comp, i) => (
              <text
                key={i}
                x={node.x + 20 + (i % 2) * 145}
                y={node.y + 95 + Math.floor(i / 2) * 28}
                fill={status.text}
                style={{ fontSize: '11px', opacity: 0.9 }}
              >
                • {comp}
              </text>
            ))}
          </g>
        )}
      </g>
    );
  };

  return (
    <div className="w-full bg-gray-50 rounded-lg p-4">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-800">Loan Pricing Pipeline</h1>
        <p className="text-gray-600">Click any node to see details • 2-Week Spike POC</p>
      </div>
      
      {/* Legend */}
      <div className="flex gap-4 mb-4 flex-wrap">
        {Object.entries(statusColors).filter(([key]) => key !== 'future').map(([key, val]) => (
          <div key={key} className="flex items-center gap-2">
            <div 
              className="w-4 h-4 rounded"
              style={{ backgroundColor: val.bg, border: `2px solid ${val.border}` }}
            />
            <span className="text-sm text-gray-600">{val.label}</span>
          </div>
        ))}
      </div>

      {/* Section Labels */}
      <div className="overflow-x-auto">
        <svg width="1200" height="420" className="bg-white rounded-lg border">
          {/* Section backgrounds - render first */}
          <rect x="45" y="40" width="180" height="340" rx="8" fill="#f8fafc" stroke="#e2e8f0" />
          <text x="135" y="58" textAnchor="middle" fill="#64748b" style={{ fontSize: '11px', fontWeight: 600 }}>INPUTS</text>
          
          <rect x="305" y="100" width="180" height="195" rx="8" fill="#f8fafc" stroke="#e2e8f0" />
          <text x="395" y="118" textAnchor="middle" fill="#64748b" style={{ fontSize: '11px', fontWeight: 600 }}>SEGMENTATION</text>
          
          <rect x="965" y="100" width="180" height="215" rx="8" fill="#f8fafc" stroke="#e2e8f0" />
          <text x="1055" y="118" textAnchor="middle" fill="#64748b" style={{ fontSize: '11px', fontWeight: 600 }}>OUTPUTS</text>
          
          {/* Connections - render second (behind nodes) */}
          {connections.map(renderConnection)}
          
          {/* Nodes - render last (on top) */}
          {Object.values(nodes).map(renderNode)}
        </svg>
      </div>

      {/* Details Panel */}
      {selectedNode && (
        <div 
          className="mt-4 bg-white rounded-lg border-2 p-4 relative"
          style={{ borderColor: statusColors[selectedNode.status].border }}
        >
          <button
            onClick={() => setSelectedNode(null)}
            className="absolute top-2 right-2 w-6 h-6 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
          
          <div className="flex justify-between items-start mb-3 pr-6">
            <h3 className="font-bold text-lg text-gray-800">{selectedNode.title}</h3>
            <span 
              className="px-2 py-1 rounded-full text-xs font-medium text-white"
              style={{ backgroundColor: statusColors[selectedNode.status].border }}
            >
              {statusColors[selectedNode.status].label}
            </span>
          </div>
          
          <p className="text-gray-600 text-sm mb-3">{selectedNode.details.description}</p>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {selectedNode.details.inputs && (
              <div>
                <h4 className="font-semibold text-sm text-gray-700 mb-1">Inputs:</h4>
                <ul className="text-sm text-gray-600 space-y-1">
                  {selectedNode.details.inputs.map((input, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-gray-400 rounded-full flex-shrink-0" />
                      {input}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {selectedNode.details.outputs && (
              <div>
                <h4 className="font-semibold text-sm text-gray-700 mb-1">Outputs:</h4>
                <ul className="text-sm text-gray-600 space-y-1">
                  {selectedNode.details.outputs.map((output, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-blue-400 rounded-full flex-shrink-0" />
                      {output}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {selectedNode.details.personas && (
              <div>
                <h4 className="font-semibold text-sm text-gray-700 mb-1">Personas:</h4>
                <ul className="text-sm text-gray-600 space-y-1">
                  {selectedNode.details.personas.map((p, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-purple-400 rounded-full flex-shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {selectedNode.details.states && (
              <div>
                <h4 className="font-semibold text-sm text-gray-700 mb-1">Loan States:</h4>
                <ul className="text-sm text-gray-600 space-y-1">
                  {selectedNode.details.states.map((s, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-green-400 rounded-full flex-shrink-0" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {selectedNode.details.components && (
              <div>
                <h4 className="font-semibold text-sm text-gray-700 mb-1">Components:</h4>
                <ul className="text-sm text-gray-600 space-y-1">
                  {selectedNode.details.components.map((c, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-blue-400 rounded-full flex-shrink-0" />
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {selectedNode.details.useCases && (
              <div>
                <h4 className="font-semibold text-sm text-gray-700 mb-1">Use Cases:</h4>
                <ul className="text-sm text-gray-600 space-y-1">
                  {selectedNode.details.useCases.map((u, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full flex-shrink-0" />
                      {u}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Model Status Table for Simulation Engine */}
          {selectedNode.details.modelNotes && (
            <div className="mt-4 p-3 bg-gray-50 rounded-lg border">
              <h4 className="font-semibold text-sm text-gray-700 mb-2">Model Status:</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {selectedNode.details.modelNotes.map((m, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="font-medium text-gray-700 min-w-20">{m.name}:</span>
                    <span className="text-gray-600">{m.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Monte Carlo Details */}
          {selectedNode.details.monteCarlo && (
            <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
              <h4 className="font-semibold text-sm text-blue-800 mb-2">🎲 Monte Carlo Simulation</h4>
              <p className="text-sm text-blue-700 mb-2">{selectedNode.details.monteCarlo.description}</p>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <h5 className="font-medium text-xs text-blue-800 mb-1">Macro Variables:</h5>
                  <ul className="text-sm text-blue-700 space-y-1">
                    {selectedNode.details.monteCarlo.macroVariables.map((v, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-blue-400 rounded-full flex-shrink-0" />
                        {v}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h5 className="font-medium text-xs text-blue-800 mb-1">Named Scenarios:</h5>
                  <ul className="text-sm text-blue-700 space-y-1">
                    {selectedNode.details.monteCarlo.namedScenarios.map((s, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full flex-shrink-0" />
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h5 className="font-medium text-xs text-blue-800 mb-1">Approach:</h5>
                  <ul className="text-sm text-blue-700 space-y-1">
                    {selectedNode.details.monteCarlo.approach.map((a, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="w-1.5 h-1.5 bg-blue-400 rounded-full flex-shrink-0 mt-1.5" />
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
          
          {/* Sprint & Logic Info */}
          <div className="mt-3 pt-3 border-t flex flex-wrap gap-4">
            {selectedNode.details.sprint && (
              <div>
                <span className="text-xs font-medium text-gray-500">Sprint: </span>
                <span className="text-xs text-gray-700">{selectedNode.details.sprint}</span>
              </div>
            )}
            {selectedNode.details.logic && (
              <div>
                <span className="text-xs font-medium text-gray-500">Logic: </span>
                <span className="text-xs text-gray-700">{selectedNode.details.logic}</span>
              </div>
            )}
          </div>
          
          {/* Warning Note */}
          {selectedNode.details.note && (
            <div className="mt-2 p-2 bg-amber-50 rounded text-xs text-amber-800 border border-amber-200">
              ⚠️ {selectedNode.details.note}
            </div>
          )}
        </div>
      )}

      {/* Task Overview - Always visible */}
      <div className="mt-4 space-y-4">
        <div className="p-4 bg-white rounded-lg border">
          <h3 className="font-bold text-gray-800 mb-3">Task Overview</h3>
          
          {/* Priority Legend */}
          <div className="flex gap-4 mb-3 text-xs">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500"></span> P1 - Critical</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500"></span> P2 - Important</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500"></span> P3 - Nice to have</span>
            <span className="text-gray-400 ml-4">Complexity: S = Simple, M = Medium, C = Complex</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            {/* Epic: Inputs */}
            <div>
              <h4 className="font-semibold text-gray-700 mb-2 pb-1 border-b">Inputs</h4>
              <ul className="space-y-1.5">
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Loan data structures</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Borrower profile structures</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Cost of capital input</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">CoC scenario correlation</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
              </ul>
            </div>

            {/* Epic: Segmentation */}
            <div>
              <h4 className="font-semibold text-gray-700 mb-2 pb-1 border-b">Segmentation</h4>
              <ul className="space-y-1.5">
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Simple persona rules</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Placeholder risk buckets</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0"></span>
                  <span className="text-gray-600 text-xs italic">Post-spike: Cluster analysis</span>
                  <span className="text-xs text-gray-400 ml-auto">C</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0"></span>
                  <span className="text-gray-600 text-xs italic">Post-spike: Data-driven buckets</span>
                  <span className="text-xs text-gray-400 ml-auto">C</span>
                </li>
              </ul>
            </div>

            {/* Epic: Simulation Engine */}
            <div>
              <h4 className="font-semibold text-gray-700 mb-2 pb-1 border-b">Simulation Engine</h4>
              <ul className="space-y-1.5">
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Loan state model</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Cash flow projection</span>
                  <span className="text-xs text-gray-400 ml-auto">C</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Integrate Survival model</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Mock DEQ (defaults)</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Mock Default model</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Mock Servicing costs</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Mock Recovery/Liquidation</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Monte Carlo framework</span>
                  <span className="text-xs text-gray-400 ml-auto">C</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Named scenarios</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
              </ul>
            </div>

            {/* Epic: Outputs */}
            <div>
              <h4 className="font-semibold text-gray-700 mb-2 pb-1 border-b">Outputs</h4>
              <ul className="space-y-1.5">
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Loan PV calculation</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Package PV rollup</span>
                  <span className="text-xs text-gray-400 ml-auto">S</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Scenario breakdown</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Distribution metrics</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 flex-shrink-0"></span>
                  <span className="text-gray-600">Streamlit demo UI</span>
                  <span className="text-xs text-gray-400 ml-auto">M</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Data & Roadmap Notes */}
        <div className="p-4 bg-white rounded-lg border">
          <h3 className="font-bold text-gray-800 mb-2">Data Sources & Future Roadmap</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <h4 className="font-semibold text-green-700">Data Sources</h4>
              <ul className="text-gray-600 mt-1 space-y-1">
                <li>• Internal historical loans (skewed to portfolio)</li>
                <li>• 43M loans public payment data (model dev)</li>
                <li>• Vendor data sources (pending approval)</li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-purple-700">Post-Spike Roadmap</h4>
              <ul className="text-gray-600 mt-1 space-y-1">
                <li>• Persona discovery via cluster analysis</li>
                <li>• Data-driven risk bucket boundaries</li>
                <li>• Backtesting against held-out loans</li>
                <li>• Model validation & documentation</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Regulatory Note */}
        <div className="p-3 bg-red-50 rounded-lg border border-red-200">
          <h4 className="font-semibold text-sm text-red-800 mb-1">⚖️ Regulatory Consideration</h4>
          <p className="text-xs text-red-700">
            If models are used to make pricing/lending decisions: data lineage tracking, 
            model documentation, audit trails, and explainability required before production.
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoanPipelineDiagram;
