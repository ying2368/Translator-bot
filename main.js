$(function(){
    $(".voiceButton").hide();
    $("#submit").click(azureTranslate);
    $("#message").keypress(function (e) {
        if (e.which == 13) {
            azureTranslate();
        }
    });

    // 各種發音按鈕的點擊事件
    $(".voiceButton").click(function () {
        var voiceType = $(this).attr('id');  // 獲取按鈕ID以選擇不同的語音
        $("#myAudio").attr("src", "/static/outputaudio_" + voiceType + ".wav?a=" + Math.random());
        $("#myAudio")[0].load();
        $("#myAudio")[0].play();
    });

});

function azureTranslate() {
    $("#chineseText").empty();
    $("#koreanText").empty();
    $(".voiceStyle").hide();

    var message = $("#message").val();
    $("#chineseText").text(message);
    var params = {
        message: message
    };
    $.post("/azure_translate", params, function (data) {
        $("#koreanText").text(data.japanese);
        $(".voiceButton").show();
    });
    $("#message").val("");
}
