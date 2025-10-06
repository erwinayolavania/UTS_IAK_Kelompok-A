document.addEventListener('DOMContentLoaded', function() {
    const colorPalette = [
        'rgba(75, 192, 192, 0.7)',
        'rgba(255, 159, 64, 0.7)',
        'rgba(255, 99, 132, 0.7)',
        'rgba(54, 162, 235, 0.7)',
        'rgba(153, 102, 255, 0.7)'
    ];
    
    const borderColorPalette = [
        'rgba(75, 192, 192, 1)',
        'rgba(255, 159, 64, 1)',
        'rgba(255, 99, 132, 1)',
        'rgba(54, 162, 235, 1)',
        'rgba(153, 102, 255, 1)'
    ];


    // Mendapatkan parameter filter dari URL
    const urlParams = new URLSearchParams(window.location.search);
    const komoditasFilter = urlParams.get('komoditas') || '';

    // Mengisi dropdown filter
    fetch('/api/komoditas')
        .then(response => response.json())
        .then(data => {
            const filterSelect = document.getElementById('komoditasFilter');
            filterSelect.innerHTML = '<option value="">Semua Komoditas</option>';
            
            data.komoditas.forEach(komoditas => {
                const option = document.createElement('option');
                option.value = komoditas;
                option.textContent = komoditas;
                if (komoditasFilter === komoditas) {
                    option.selected = true;
                }
                filterSelect.appendChild(option);
            });
        })
        .catch(error => console.error('Error fetching komoditas:', error));

    // 1. Grafik Batang Horizontal (Komoditas)
    fetch('/api/data-grafik')
        .then(response => response.json())
        .then(data => {
            const ctx = document.getElementById('komoditasChart').getContext('2d');
            
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: 'Total Volume (Ton)',
                        data: data.values,
                        backgroundColor: colorPalette,
                        borderColor: borderColorPalette,
                        borderWidth: 1
                    }]
                },
                options: {
                    indexAxis: 'y',
                    scales: {
                        x: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Volume (Ton)'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        title: {
                            display: true,
                            text: 'Total Volume Ekspor per Komoditas (Ton)',
                            font: {
                                size: 16
                            }
                        }
                    }
                }
            });
        })
        .catch(error => console.error('Error fetching bar chart data:', error));

    // 2. Grafik Pie (Persentase Komoditas)
    fetch('/api/data-pie')
        .then(response => response.json())
        .then(data => {
            const ctx = document.getElementById('pieChart').getContext('2d');
            
            new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.values,
                        backgroundColor: colorPalette,
                        borderColor: borderColorPalette,
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'right',
                        },
                        title: {
                            display: true,
                            text: 'Persentase Volume Komoditas (Ton)',
                            font: {
                                size: 16
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = context.raw || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = Math.round((value / total) * 100);
                                    return `${label}: ${value.toLocaleString()} Ton (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            });
        })
        .catch(error => console.error('Error fetching pie chart data:', error));

    // 3. Grafik Batang (Trend Tahunan) dengan Filter
    function updateBarChart(komoditas = '') {
        let url = '/api/data-tren';
        if (komoditas) {
            url += `?komoditas=${encodeURIComponent(komoditas)}`;
        }
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                const ctx = document.getElementById('lineChart').getContext('2d');
                
                // Hapus chart lama jika ada
                if (window.lineChartInstance) {
                    window.lineChartInstance.destroy();
                }
                
                window.lineChartInstance = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: komoditas ? `Volume Ekspor ${komoditas} (Ton)` : 'Total Volume Ekspor (Ton)',
                            data: data.values,
                            backgroundColor: 'rgba(54, 162, 235, 0.6)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Volume (Ton)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: 'Tahun'
                                }
                            }
                        },
                        plugins: {
                            legend: { display: false }, // hide legend (since only 1 dataset)
                            title: {
                                display: true,
                                text: komoditas ? `Trend Volume Ekspor ${komoditas} Tahunan` : 'Trend Volume Ekspor Tahunan',
                                font: { size: 16 }
                            }
                        }
                    }
                });
            })
            .catch(error => console.error('Error fetching bar chart data:', error));
    }


    // 4. Grafik Garis Trend Semua Komoditas
    fetch('/api/data-tren-all-komoditas')
        .then(res => res.json())
        .then(data => {
            // Hide loading spinner
            document.getElementById('loadingLineChartAll').style.display = 'none';

            const ctx = document.getElementById('lineChartAll').getContext('2d');

            // Destroy previous chart instance if exists
            if (window.lineChartAllInstance) window.lineChartAllInstance.destroy();

            // Create new chart
            window.lineChartAllInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: data.datasets.map((dataset, i) => ({
                        label: dataset.label,
                        data: dataset.data,
                        borderColor: borderColorPalette[i % borderColorPalette.length],
                        backgroundColor: colorPalette[i % colorPalette.length].replace('0.7', '0.2'),
                        fill: false,
                        tension: 0.3,
                        pointRadius: 4
                    }))
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true, title: { display: true, text: 'Volume (Ton)' } },
                        x: { title: { display: true, text: 'Tahun' } }
                    },
                    plugins: {
                        legend: { position: 'bottom' },
                        title: {
                            display: true,
                            text: 'Trend Volume Ekspor Semua Komoditas',
                            font: { size: 16 }
                        }
                    }
                }
            });
        })
        .catch(err => {
            console.error('Error fetching line chart data:', err);
            document.getElementById('loadingLineChartAll').innerHTML =
                '<i class="fas fa-exclamation-triangle"></i> Gagal memuat grafik';
        });


    // Inisialisasi grafik garis
    updateBarChart(komoditasFilter);

    // Event listener untuk filter
    document.getElementById('komoditasFilter').addEventListener('change', function() {
        const selectedKomoditas = this.value;
        const url = new URL(window.location);
        
        if (selectedKomoditas) {
            url.searchParams.set('komoditas', selectedKomoditas);
        } else {
            url.searchParams.delete('komoditas');
        }
        
        // Reset ke halaman 1 saat mengubah filter
        url.searchParams.set('page', 1);
        
        window.location.href = url.toString();
    });

    // Event listener untuk reset filter
    document.getElementById('resetFilter').addEventListener('click', function() {
        const url = new URL(window.location);
        url.searchParams.delete('komoditas');
        url.searchParams.set('page', 1);
        window.location.href = url.toString();
    });
});