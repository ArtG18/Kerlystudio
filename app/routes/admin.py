{% extends "base.html" %}
{% block content %}

<h2 class="mb-4">Dashboard 💅</h2>

<div class="row text-center">

<div class="col-md-3">
<h4>💸 ${{ stats.ingresos_hoy }}</h4>
<p>Hoy</p>
</div>

<div class="col-md-3">
<h4>{{ stats.citas_hoy }}</h4>
<p>Citas hoy</p>
</div>

<div class="col-md-3">
<h4>{{ stats.pendientes }}</h4>
<p>Pendientes</p>
</div>

<div class="col-md-3">
<h4>{{ stats.confirmadas }}</h4>
<p>Confirmadas</p>
</div>

</div>

{% endblock %}